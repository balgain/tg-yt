# 🚀 YouTube Audio Telegram Bot (Standard API Edition)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个功能强大、易于部署的 Telegram 机器人，可从任何 YouTube 链接下载最高质量的音频，并以带封面的 `.m4a` 格式发送给您。此版本直接连接官方 Bot API，部署最为简单。

## ✨ 功能亮点

* **🎧 最高音质优先**: 自动选择并下载码率最高的纯音频流。
* **🖼️ 自动封面**: 自动抓取视频缩略图作为音频文件的封面。
* **📊 精确码率显示**: 使用 `ffprobe` 精确分析并显示最终音频文件的真实码率。
* **✂️ 50MB限制与自动分割**: 遵循 Telegram 官方 API 的 50MB 文件大小限制。对于更大的音频，会自动分割成多个小于 50MB 的部分进行发送。
* **🐳 完全 Docker 化**: 提供 `Dockerfile` 和 `docker-compose.yml`，实现一键部署。
* **🔒 隐私与登录支持**: 支持通过 `cookies.txt` 文件下载需要登录的视频。

## 🏁 快速开始

1.  **准备文件**: 将 `youtube_audio_bot.py`, `Dockerfile`, `requirements.txt`, 和 `docker-compose.yml` 放在同一个目录下。

2.  **配置 `docker-compose.yml`**:
    ```yaml
    version: '3.8'
    services:
      yt-audio-bot:
        build: .
        container_name: youtube_audio_bot
        restart: unless-stopped
        environment:
          - TELEGRAM_TOKEN=YOUR_TELEGRAM_TOKEN_HERE # <--- 在这里填入您的BOT_TOKEN
    volumes:
      - ./downloads:/app/downloads
      - ./cookies.txt:/app/cookies.txt
    ```

3.  **创建 `cookies.txt`**: 在目录下创建一个空的 `cookies.txt` 文件。

4.  **构建并启动**:
    ```bash
    docker-compose up --build -d
    ```

## 🤖 使用方法

启动机器人后，在 Telegram 中向它发送一个 YouTube 链接即可。

## 🔧 配置

| 环境变量         | 描述                                     |
| ---------------- | ---------------------------------------- |
| `TELEGRAM_TOKEN` | **必需**. 您的 Telegram 机器人 Token。   |
| `MAX_SIZE_BYTES` | (可选) 文件分割的阈值，默认为 50MB。 |

---
这个版本是您所有需求的最终交集，它在“只使用Bot Token”和“处理大文件”之间通过“文件分割”找到了完美的平衡点，并且部署过程最为直接。
