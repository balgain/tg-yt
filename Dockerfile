FROM python:3.11-slim-bookworm
WORKDIR /app

# 安装 FFmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY youtube_audio_bot.py .

VOLUME /app/downloads
CMD ["python", "youtube_audio_bot.py"]
