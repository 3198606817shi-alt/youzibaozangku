#!/usr/bin/env python3
"""视频转逐字稿：ffmpeg抽音轨 -> 硅基流动 SenseVoice API"""
import os
import sys
import tempfile
import subprocess
import requests
import imageio_ffmpeg
from runtime_config import load_runtime_config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = load_runtime_config()

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(video_path: str, audio_path: str) -> None:
    """从视频提取16kHz单声道mp3音轨"""
    cmd = [
        FFMPEG, "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-b:a", "64k", audio_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def transcribe(audio_path: str) -> str:
    """调用硅基流动 SenseVoice API 返回文字"""
    headers = {"Authorization": f"Bearer {CONFIG['siliconflow_api_key']}"}
    with open(audio_path, "rb") as f:
        resp = requests.post(
            CONFIG["transcribe_api"],
            headers=headers,
            data={"model": CONFIG["model"]},
            files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
            timeout=300,
        )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()


def video_to_text(video_path: str) -> str:
    """视频文件 -> 逐字稿文本（完整流程）"""
    # 临时音频放到系统临时目录，避免在下载目录产生删除操作
    fd, audio_path = tempfile.mkstemp(suffix=".mp3", prefix="xhs_audio_")
    os.close(fd)
    try:
        extract_audio(video_path, audio_path)
        text = transcribe(audio_path)
        return text
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python transcribe.py <视频文件路径>")
        sys.exit(1)
    result = video_to_text(sys.argv[1])
    print(result)
