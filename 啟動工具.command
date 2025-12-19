#!/bin/bash

# 1. 切換到腳本所在的資料夾
cd "$(dirname "$0")"

echo "------------------------------------------"
echo "   YouTube Shorts AI 分析工具 - Mac 啟動器"
echo "------------------------------------------"

# 2. 檢查 Python 環境
if ! command -v python3 &> /dev/null
then
    echo "❌ 錯誤：找不到 Python3。請先安裝 Python (https://www.python.org/)"
    exit
fi

# 3. 安裝/更新 必要套件
echo "📦 正在檢查依賴套件 (google-genai, yt-dlp, pandas...)"
python3 -m pip install -q --upgrade pip
python3 -m pip install -q google-genai google-api-python-client yt-dlp pandas pyperclip requests

# 4. 啟動程式
echo "🚀 正在開啟程式，請稍候..."
python3 ShortWithGeminiPrompt.py

# 結束後暫停視窗
read -p "程式已關閉，按任意鍵退出..."
