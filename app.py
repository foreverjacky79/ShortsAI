import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
import google.generativeai as genai
import re

# 配置
st.set_page_config(layout="wide", page_icon="🎥", page_title="YouTube Shorts 分析工具")

@st.cache_data(ttl=300)
# == search YT and create prompt ==
def fetch_trending_shorts(api_key, keyword, days, min_views, max_results, min_viral_score, max_duration):
    """YouTube Shorts 趨勢搜尋（無 yt_dlp）"""
    youtube = build("youtube", "v3", developerKey=api_key)
    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 只搜短影片
    search_response = youtube.search().list(
        q=f"{keyword} shorts", 
        part="id,snippet", 
        type="video", 
        order="viewCount", 
        maxResults=max_results, 
        videoDuration="short",
        publishedAfter=published_after
    ).execute()

    video_ids = [item["id"]["videoId"] for item in search_response["items"] if item["id"]["videoId"]]
    if not video_ids: return []

    # 詳細資料
    video_response = youtube.videos().list(
        part="snippet,statistics,contentDetails", 
        id=",".join(video_ids[:50])
    ).execute()

    results = []
    for item in video_response.get("items", []):
        duration_raw = item["contentDetails"]["duration"]
        total_seconds = parse_duration_to_seconds(duration_raw)
        if total_seconds > max_duration: continue

        stats = item.get("statistics", {})
        snippet = item["snippet"]
        views = int(stats.get("viewCount", 0))
        if views < min_views: continue

        published = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours_passed = max((now - published).total_seconds() / 3600, 1)
        viral_score = views / hours_passed
        
        if viral_score < min_viral_score: continue

        m, s = divmod(total_seconds, 60)
        results.append({
            "title": snippet["title"][:80],
            "views": views,
            "duration": f"{m}:{s:02d}",
            "hours": round(hours_passed, 1),
            "viral_score": round(viral_score, 2),
            "published": published.strftime("%m-%d %H:%M"),
            "url": f"https://youtube.com/watch?v={item['id']}"
        })
    
    return sorted(results, key=lambda x: x["viral_score"], reverse=True)

def parse_duration_to_seconds(duration_str):
    h = re.search(r'(\d+)H', duration_str)
    m = re.search(r'(\d+)M', duration_str)
    s = re.search(r'(\d+)S', duration_str)
    return (int(h.group(1)) if h else 0)*3600 + (int(m.group(1)) if m else 0)*60 + (int(s.group(1)) if s else 0)

def ai_generate_prompt(gemini_api_key, video_url):
    """純文字 AI Prompt 生成"""
    try:
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""Create detailed English prompt for AI video generation recreating YouTube Shorts: {video_url}

Essential elements:
• Main character description (appearance, clothing, expression)
• Specific actions/movements  
• Environment/setting details
• Camera movements (zoom, pan, close-up)
• Lighting and color atmosphere
• 15-30 second duration suggestion

Single paragraph, optimized for Sora/Runway/RunwayML."""
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Gemini API 需要設定\n錯誤: {str(e)}"

# == current version ==
@st.cache_data(ttl=3600)
def get_current_version():
    try:
        return requests.get("https://raw.githubusercontent.com/foreverjacky79/ShortsAI/refs/heads/main/version.txt", timeout=5).text.strip()
    except:
        return "1.0.5"

version = get_current_version()

# ===== 美觀 Title + 版本（替換你的 st.markdown）=====
# Title + 版號（往下移版號）
st.title("🎥 YouTube Shorts 趨勢分析工具")
st.markdown(" ")  
st.caption(f"**v{version}**")

# == Sidebar ==
st.sidebar.header("🔑 API 金鑰")
api_key = st.sidebar.text_input("YouTube API Key", type="password", 
                               help="console.cloud.google.com → YouTube Data API v3")
gemini_key = st.sidebar.text_input("Gemini API Key", type="password", 
                                  help="aistudio.google.com/app/apikey")

st.sidebar.header("🔍 搜尋設定")
col1, col2 = st.sidebar.columns(2)
keyword = col1.text_input("關鍵字", value="animal")
days = col2.number_input("最近天數", 1, 14, 7)

col3, col4 = st.sidebar.columns(2)
min_views = col3.number_input("最低觀看數", 10000, 1000000, 50000)
max_duration = col4.number_input("最長秒數", 0, 60, 20)

col5, col6 = st.sidebar.columns(2)
min_viral = col5.number_input("最低爆發指數", 500.0, 10000.0, 3000.0)
max_results = col6.number_input("最大結果", 20, 100, 50)

# 搜尋按鈕
if st.sidebar.button("🚀 開始分析", type="primary", use_container_width=True):
    if not api_key:
        st.sidebar.error("❌ 需要 YouTube API Key")
        st.stop()
    with st.spinner("🔍 搜尋熱門 Shorts 中..."):
        results = fetch_trending_shorts(api_key, keyword, days, min_views, max_results, min_viral, max_duration)
        st.session_state.results = results
        if results:
            st.success(f"✅ 找到 {len(results)} 個符合條件的熱門影片！")
        else:
            st.warning("⚠️ 未找到符合條件的影片，請調整搜尋條件")
        st.rerun()

# 結果展示
if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    
    st.markdown(f"## 📊 搜尋結果 ({len(df)} 筆)")
    
    # 選擇器
    selected_idx = st.selectbox(
        "🎯 選擇影片分析：",
        range(len(df)),
        format_func=lambda i: f"🔥 {df.iloc[i]['title'][:60]}... | {df.iloc[i]['views']:,}觀看 | 爆發指數 {df.iloc[i]['viral_score']:.0f}"
    )
    
    selected = df.iloc[selected_idx]
    
    # 資訊卡片
    col1, col2, col3 = st.columns(3)
    col1.metric("👀 觀看數", f"{selected['views']:,}", f"{selected['viral_score']:.0f}")
    col2.metric("⏱️ 時長", selected['duration'])
    col3.metric("🕐 發布", f"{selected['hours']}小時前")
    
    st.markdown(f"**{selected['title']}**")
    st.markdown(f"[🔗 觀看原影片]({selected['url']})")
    
    # 動作列
    col1, col2 = st.columns(2)
    if col1.button("🤖 生成 AI Prompt", type="primary", use_container_width=True, disabled=not gemini_key):
        if gemini_key:
            with st.spinner("🎨 AI 生成中..."):
                result = ai_generate_prompt(gemini_key, selected['url'])
                st.session_state.ai_result = result
                st.success("✅ AI Prompt 生成完成！")
    
    # 完整表格
    st.markdown("### 📋 完整搜尋結果")
    st.dataframe(
        df[['title', 'views', 'viral_score', 'duration', 'published']],
        use_container_width=True,
        column_config={
            "views": st.column_config.NumberColumn("觀看數", format="%,d"),
            "viral_score": st.column_config.NumberColumn("爆發指數", format="%.1f")
        },
        hide_index=True
    )

# AI Prompt 結果
if "ai_result" in st.session_state:
    st.markdown("## 🎨 AI 生成的影片 Prompt")
    st.code(st.session_state.ai_result, language=None)
    
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "💾 下載 Prompt.txt",
            data=st.session_state.ai_result,
            file_name="youtube_shorts_ai_prompt.txt",
            mime="text/plain"
        )
    with col2:
        st.markdown("### 📋 直接複製")
        st.code(st.session_state.ai_result)

# 使用說明
with st.expander("📖 使用說明 & API 申請"):
    st.markdown("""
    ### 🚀 快速上手
    1. **側邊欄**填入 **YouTube API Key**
    2. 調整搜尋條件 → **開始分析**
    3. 選擇熱門影片 → **生成 AI Prompt**
    4. 複製 Prompt 到 **Sora/Runway/Kling** 等 AI 工具
    
    ### 🔑 API Key 申請
    **YouTube Data API v3**（免費，每日10,000次）：
    1. [Google Cloud Console](https://console.cloud.google.com)
    2. 新建專案 → 啟用 **YouTube Data API v3**
    3. 憑證 → **API Key** → 複製
    
    **Gemini API**（免費，每分鐘15次）：
    1. [Google AI Studio](https://aistudio.google.com/app/apikey)
    2. **Get API Key** → 複製
    
    ### 💡 搜尋技巧
    - **關鍵字**：`cat` `dog` `cooking` `dance`
    - **天數**：1-3天最熱門，7天較全面
    - **爆發指數**：2000+ = 病毒式傳播
    """)
