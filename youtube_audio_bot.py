import logging
import os
import re
import math
import yt_dlp
import asyncio
import subprocess
import glob
import uuid
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from typing import List

# --- 1. 配置 ---

# 机器人Token，从环境变量读取
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE") 

# 浏览器User-Agent
BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# 文件大小限制，默认为50MB (Telegram Bot API 官方限制)
MAX_SIZE_BYTES = int(os.getenv("MAX_SIZE_BYTES", 50 * 1024 * 1024))

# 临时文件目录
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")

# Cookie文件路径
COOKIE_FILE = "cookies.txt"

# --- 日志记录 ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 确保下载目录存在 ---
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


async def get_exact_bitrate(file_path: str) -> str:
    """使用ffprobe分析文件，获取精确的码率。"""
    try:
        command = [
            'ffprobe', '-v', 'error', '-select_streams', 'a:0',
            '-show_entries', 'stream=bit_rate', '-of', 'default=noprint_wrappers=1:nokey=1', file_path
        ]
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0 and stdout:
            bitrate_bps = int(stdout.decode().strip())
            return f"{round(bitrate_bps / 1000)}kbs"
        return "N/A"
    except Exception as e:
        logger.error(f"获取码率时出错: {e}")
        return "N/A"


async def split_audio_by_segment(input_file: str, total_duration: float, file_size: int, max_chunk_size: int, output_prefix: str) -> List[str]:
    """使用FFmpeg将大文件分割成小于50MB的块。"""
    if total_duration <= 0 or file_size <= max_chunk_size:
        return []

    bytes_per_second = file_size / total_duration
    segment_duration = math.floor((max_chunk_size / bytes_per_second) * 0.98)
    
    if segment_duration <= 0:
        logger.warning("计算出的分割时长过小，跳过分割。")
        return []

    output_pattern = f"{output_prefix}_part_%03d.m4a"
    full_output_path = os.path.join(DOWNLOAD_DIR, output_pattern)

    command = [
        'ffmpeg', '-i', input_file, '-f', 'segment',
        '-segment_time', str(segment_duration), '-c', 'copy',
        '-map', '0:a', '-y', full_output_path
    ]

    logger.info(f"正在执行FFmpeg分割命令: {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()

    if process.returncode != 0:
        logger.error(f"FFmpeg分割失败，退出码: {process.returncode}")
        return []
    
    split_files = sorted(glob.glob(os.path.join(DOWNLOAD_DIR, f"{output_prefix}_part_*.m4a")))
    logger.info(f"成功分割成 {len(split_files)} 个部分。")
    return split_files


class AudioDownloader:
    """封装了单次下载、处理和发送任务的完整逻辑"""
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        self.update = update
        self.context = context
        self.url = url
        self.chat_id = self.update.message.chat_id
        self.original_message_id = self.update.message.message_id
        self.processing_message = None
        self.unique_id = str(uuid.uuid4())
        self.files_to_delete = []

    async def process(self):
        try:
            self.processing_message = await self.context.bot.send_message(self.chat_id, "正在解析链接...")
            
            ydl_opts_info = {
                'quiet': True, 'no_warnings': True, 'cookiefile': COOKIE_FILE,
                'format': 'bestaudio/best', 'http_headers': {'User-Agent': BROWSER_USER_AGENT},
            }
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info_dict = ydl.extract_info(self.url, download=False)
            
            if not info_dict.get('acodec') or info_dict.get('acodec') == 'none':
                await self.edit_message("抱歉，无法找到任何有效的音频流。")
                return

            selected_format = info_dict
            thumbnail_url = info_dict.get('thumbnail')
            
            output_template = os.path.join(DOWNLOAD_DIR, f'{self.unique_id}.%(ext)s')
            output_filename = os.path.join(DOWNLOAD_DIR, f"{self.unique_id}.m4a")
            self.files_to_delete.append(output_filename)
            
            ydl_opts_download = {
                'format': selected_format['format_id'], 'outtmpl': output_template,
                'cookiefile': COOKIE_FILE, 'quiet': True,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a'}],
                'http_headers': {'User-Agent': BROWSER_USER_AGENT}
            }
            
            await self.edit_message(f"已选择最高音频质量 (估算: {selected_format.get('abr', 'N/A')}kbs)，开始下载...")

            with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
                ydl.download([self.url])

            if not os.path.exists(output_filename):
                possible_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{self.unique_id}.*"))
                if possible_files:
                    os.rename(possible_files[0], output_filename)
                else:
                    await self.edit_message("下载失败或找不到文件。")
                    return
            
            exact_bitrate = await get_exact_bitrate(output_filename)
            file_size = os.path.getsize(output_filename)
            video_title = info_dict.get('title', 'Audio')
            duration = info_dict.get('duration', 0)

            if file_size < MAX_SIZE_BYTES:
                await self.edit_message(f"下载完成 (精确码率: {exact_bitrate})，正在发送...")
                with open(output_filename, 'rb') as audio_file:
                    await self.context.bot.send_audio(
                        chat_id=self.chat_id, audio=audio_file, title=video_title, 
                        duration=duration, thumbnail=thumbnail_url
                    )
            else:
                await self.edit_message(f"文件过大 ({round(file_size / (1024*1024), 2)}MB)，正在分割成 <50MB 的小块...")
                split_files = await split_audio_by_segment(output_filename, duration, file_size, MAX_SIZE_BYTES, self.unique_id)
                self.files_to_delete.extend(split_files)

                if not split_files:
                    await self.edit_message("分割文件失败，请检查服务器日志。")
                    return

                for i, part_path in enumerate(split_files):
                    await self.edit_message(f"正在发送第 {i + 1}/{len(split_files)} 部分...")
                    with open(part_path, 'rb') as chunk_file:
                        await self.context.bot.send_audio(
                            chat_id=self.chat_id, audio=chunk_file,
                            title=f"{video_title} (Part {i+1}/{len(split_files)})",
                            thumbnail=thumbnail_url
                        )
        except Exception as e:
            logger.error(f"处理链接 {self.url} 时发生错误: {e}", exc_info=True)
            error_message = f"处理时发生错误: {type(e).__name__}"
            if "private video" in str(e).lower(): error_message = "抱歉，这是一个私有视频。"
            await self.edit_message(error_message)
        finally:
            if self.processing_message:
                try: await self.context.bot.delete_message(self.chat_id, self.processing_message.message_id)
                except Exception: pass
            
            for f in self.files_to_delete:
                if os.path.exists(f):
                    try: os.remove(f)
                    except Exception: pass

    async def edit_message(self, text: str):
        if self.processing_message:
            try: await self.context.bot.edit_message_text(text, self.chat_id, self.processing_message.message_id)
            except Exception: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("你好！请发送一个YouTube链接给我。")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text: return
    
    youtube_regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=)?(?:live\/)?(?:shorts\/)?([a-zA-Z0-9_-]{11})"
    match = re.search(youtube_regex, message_text := update.message.text)
    
    if match:
        asyncio.create_task(AudioDownloader(update, context, match.group(0)).process())
    else:
        await update.message.reply_text("请发送一个有效的YouTube链接。")

def main() -> None:
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_TOKEN_HERE":
        logger.critical("请在环境变量或脚本中设置您的 TELEGRAM_TOKEN！")
        return

    # 不再需要配置base_url，直接使用官方API
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("机器人已启动，连接到官方 Telegram Bot API...")
    application.run_polling()

if __name__ == "__main__":
    main()
