import streamlit as st
import requests
import json
import os
import webbrowser
import time
import pandas as pd
import yt_dlp
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
import google.generativeai as genai
import pyperclip
import re
import threading

# ===== 核心函數（必須放在最前面）=====
@st.cache_data(ttl=300)
def fetch_trending_shorts(api_key, keyword, days, min_views, min_subs, max_results, min_viral_score, max_duration):
    """YouTube Shorts 趨勢搜尋"""
    youtube = build("youtube", "v3", developerKey=api_key)
    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    search_response = youtube.search().list(
        q=keyword, part="id", type="video", order="viewCount",
        maxResults=max_results, publishedAfter=published_after
    ).execute()

    video_ids = [item["id"]["videoId"] for item in search_response["items"]]
    if not video_ids: return []

    video_response = youtube.videos().list(
        part="snippet,statistics,contentDetails", id=",".join(video_ids)
    ).execute()

    results = []
    for item in video_response["items"]:
        duration_raw = item["contentDetails"]["duration"]
        total_seconds = parse_duration_to_seconds(duration_raw)
        if total_seconds > max_duration: continue

        stats = item["statistics"]
        snippet = item["snippet"]
        views = int(stats.get("viewCount", 0))
        if views < min_views: continue

        published = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours_passed = max((now - published).total_seconds() / 3600, 1)
        viral_score = views / hours_passed
        
        if viral_score < min_viral_score: continue

        m, s = divmod(total_seconds, 60)
        duration_display = f"{m}:{s:02d}"

        results.append({
            "title": snippet["title"],
            "views": views,
            "duration": duration_display,
            "hours": round(hours_passed, 1),
            "viral_score": round(viral_score, 2),
            "published": published.strftime("%Y-%m-%d %H:%M"),
            "url": f"https://www.youtube.com/watch?v={item['id']}"
        })

    results.sort(key=lambda x: x["viral_score"], reverse=True)
    return results

def parse_duration_to_seconds(duration_str):
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    seconds = re.search(r'(\d+)S', duration_str)
    h = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    s = int(seconds.group(1)) if seconds else 0
    return h * 3600 + m * 60 + s

def ai_generate_prompt(gemini_api_key, video_url, progress_callback=None):
    """簡化版 AI Prompt 生成（無需下載影片）"""
    if not gemini_api_key:
        return "⚠️ 請輸入 Gemini API Key！"
    
    try:
        if progress_callback: progress_callback("🧠 AI 生成範例 Prompt...")
        
        # 直接用文字生成 Prompt（部署環境限制影片上傳）
        client = genai.GenerativeModel('gemini-1.5-flash')
        client.api_key = gemini_api_key  # 部署環境用此方式
        
        prompt = f"""
        請為 YouTube Shorts "{video_url}" 生成 AI 影片重製的英文 Prompt。
        包含：角色特徵、動作、環境、鏡頭運動、光影氛圍。
        格式：單一段落，適合 Sora/Runway 使用。
        """
        
        response = client.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ 分析失敗: {str(e)}\n建議：使用本地版本完整功能"

@st.cache_data(ttl=300)
def get_current_version():
    try:
        response = requests.get("https://raw.githubusercontent.com/foreverjacky79/ShortsAI/refs/heads/main/version.txt", timeout=5)
        return response.text.strip()
    except:
        return "1.0.5"

# ===== Streamlit UI（函數定義後）=====
st.set_page_config(page_title="YouTube Shorts 趨勢分析", page_icon="🎥", layout="wide")

st.title(f"🎥 YouTube Shorts 趨勢分析工具 v{get_current_version()}")

# Sidebar
st.sidebar.header("⚙️ 設定")
api_key = st.sidebar.text_input("YouTube API Key", type="password")
gemini_key = st.sidebar.text_input("Gemini API Key", type="password")

st.sidebar.header("🔍 搜尋條件")
col1, col2 = st.sidebar.columns(2)
keyword = col1.text_input("關鍵字", "animal")
days = col2.number_input("天數", 1, 30, 7)

col3, col4 = st.sidebar.columns(2)
min_views = col3.number_input("最低觀看", 10000, 1000000, 100000)
max_duration = col4.number_input("最長秒數", 10, 60, 20)

col5, col6 = st.sidebar.columns(2)
min_viral = col5.number_input("爆發指數", 1000.0, 10000.0, 3000.0)
max_results = col6.number_input("最大結果", 10, 100, 30)

# 搜尋按鈕
if st.sidebar.button("🚀 開始搜尋", type="primary"):
    if api_key:
        with st.spinner("搜尋中..."):
            results = fetch_trending_shorts(api_key, keyword, days, min_views, 0, max_results, min_viral, max_duration)
            st.session_state.results = results
            st.success(f"找到 {len(results)} 個熱門 Shorts！")
    else:
        st.error("請輸入 YouTube API Key")

# 主介面
if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    df = df.sort_values("viral_score", ascending=False)
    
    st.subheader(f"📊 搜尋結果 ({len(df)} 筆)")
    
    # 選擇影片
    selected_idx = st.selectbox("選擇影片：", range(len(df)), 
                               format_func=lambda i: f"{df.iloc[i]['title'][:50]}... ({df.iloc[i]['views']:,}觀看)")
    
    selected = df.iloc[selected_idx]
    
    # 影片資訊
    col1, col2, col3 = st.columns(3)
    col1.metric("觀看數", f"{selected['views']:,}", f"{selected['viral_score']:.0f}")
    col2.metric("時長", selected['duration'])
    col3.metric("發布", f"{selected['hours']}小時前")
    
    st.info(selected['title'])
    
    # 動作按鈕
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🌐 開啟影片"): webbrowser.open(selected['url'])
    with col2:
        if st.button("📋 複製連結"): 
            pyperclip.copy(selected['url'])
            st.success("已複製！")
    with col3:
        if st.button("🤖 AI 分析", disabled=not gemini_key):
            if gemini_key:
                with st.spinner("AI 分析中..."):
                    result = ai_generate_prompt(gemini_key, selected['url'])
                    st.session_state.ai_result = result
    
    # 完整表格
    st.dataframe(df[['title', 'views', 'duration', 'viral_score', 'published']], 
                use_container_width=True)
    
    # AI 結果
    if "ai_result" in st.session_state:
        st.subheader("🎨 AI 生成的 Prompt")
        st.code(st.session_state.ai_result)
        st.download_button("下載", st.session_state.ai_result, "prompt.txt")

# 手動分析
st.subheader("🔗 手動輸入 URL")
manual_url = st.text_input("YouTube 連結")
if st.button("AI 分析", disabled=not gemini_key or not manual_url):
    if gemini_key:
        with st.spinner("分析中..."):
            result = ai_generate_prompt(gemini_key, manual_url)
            st.session_state.ai_result = result
