import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import webbrowser
import time
import pandas as pd
import yt_dlp
#from datetime import datetime, UTC, timedelta
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from google import genai  # 新增：Gemini SDK
import pyperclip
import sys
import requests
import re
CURRENT_VERSION = "1.0.2"  # 當前版本
UPDATE_URL = "https://raw.githubusercontent.com/foreverjacky79/ShortsAI/refs/heads/main/README.md"
CODE_URL = "https://raw.githubusercontent.com/foreverjacky79/ShortsAI/refs/heads/main/ShortWithGeminiPrompt.py"

def parse_duration_to_seconds(duration_str):
    """ 將 YouTube 的 PT1M5S 格式轉換為總秒數 """
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    seconds = re.search(r'(\d+)S', duration_str)
    
    h = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    s = int(seconds.group(1)) if seconds else 0
    
    return h * 3600 + m * 60 + s

def check_for_updates():
    try:
        # 1. 檢查雲端版本號
        response = requests.get(UPDATE_URL, timeout=5)
        latest_version = response.text.strip()

        if latest_version > CURRENT_VERSION:
            answer = messagebox.askyesno("發現更新", f"偵測到新版本 {latest_version}，是否要自動更新？\n(更新後請重啟程式)")
            if answer:
                # 2. 下載最新代碼
                new_code = requests.get(CODE_URL).text
                
                # 3. 取得目前執行檔案的路徑並覆蓋
                current_file_path = os.path.abspath(__file__)
                with open(current_file_path, "w", encoding="utf-8") as f:
                    f.write(new_code)
                
                messagebox.showinfo("更新成功", "程式已更新完成，請關閉後重新開啟。")
                root.destroy() # 關閉目前視窗
    except Exception as e:
        print(f"檢查更新失敗: {e}")

def get_base_path():
    """ 取得程式執行的真實路徑 """
    if getattr(sys, 'frozen', False):
        # 這是打包後的 .exe 執行路徑
        return os.path.dirname(sys.executable)
    # 這是開發環境的 .py 路徑
    return os.path.dirname(os.path.abspath(__file__))

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc

# ========================
# Core Logic: YouTube Fetcher
# ========================
def fetch_trending_shorts(api_key, keyword, days, min_views, min_subs, max_results, min_viral_score, max_duration):
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
        # 1. 先抓取內容時長並過濾
        duration_raw = item["contentDetails"]["duration"]
        total_seconds = parse_duration_to_seconds(duration_raw)
        
        if total_seconds > max_duration: 
            continue

        # 2. 定義基本變數 (必須在 append 之前定義！)
        stats = item["statistics"]
        snippet = item["snippet"]
        views = int(stats.get("viewCount", 0))
        
        # 3. 觀看數過濾
        if views < min_views: 
            continue

        # 4. 計算爆發指數與時間
        published = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours_passed = max((now - published).total_seconds() / 3600, 1)
        viral_score = views / hours_passed
        
        # 5. 爆發指數過濾
        if viral_score < min_viral_score: 
            continue

        # 6. 格式化顯示時長
        m, s = divmod(total_seconds, 60)
        duration_display = f"{m}:{s:02d}"

        # 7. 最後才加入結果清單 (只需一次 append)
        results.append({
            "title": snippet["title"],
            "views": views,
            "duration": duration_display,
            "hours": round(hours_passed, 1),
            "viral_score": round(viral_score, 2),
            "published": published.strftime("%Y-%m-%d %H:%M"),
            "url": f"https://www.youtube.com/watch?v={item['id']}"
        })

    # 排序並回傳
    results.sort(key=lambda x: x["viral_score"], reverse=True)
    return results

# ========================
# Core Logic: Gemini AI Analysis
# ========================
def ai_generate_prompt(gemini_api_key, video_url, progress_callback):
    """
    下載影片並由 Gemini 產生提示詞
    """
    if not gemini_api_key:
        return "⚠️ 請先在【進階設定】輸入 Gemini API Key！"
    
    try:
        progress_callback("正在下載影片片段...")
        # --- 新增：獲取內置 ffmpeg 的路徑 ---
        """ ffmpeg_path = resource_path(".") # 指向臨時資料夾根目錄
        
        ydl_opts = {
            'format': 'best[ext=mp4]/tiny',
            'outtmpl': 'temp_ai_input.mp4',
            'overwrites': True,
            # 強制指定 ffmpeg 的位置
            'ffmpeg_location': ffmpeg_path 
        }        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url]) """

        ydl_opts = {
            'format': 'best[ext=mp4]/tiny',
            'outtmpl': 'temp_ai_input.mp4',
            'overwrites': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        client = genai.Client(api_key=gemini_api_key)
        
        # 獲取可用模型
        models_list = [m.name for m in client.models.list()]
        #priority_models = ["models/gemini-2.0-flash-exp", "models/gemini-1.5-flash", "models/gemini-1.5-pro"]
        priority_models = ["models/gemini-2.0-flash-exp"]
        target_model = next((p for p in priority_models if p in models_list), models_list[0])

        progress_callback(f"正在上傳至 Gemini ({target_model})...")
        with open("temp_ai_input.mp4", "rb") as f:
            video_file = client.files.upload(file=f, config={'mime_type': 'video/mp4'})

        while video_file.state == "PROCESSING":
            time.sleep(2)
            video_file = client.files.get(name=video_file.name)

        progress_callback("AI 正在分析內容...")
        prompt_instruction = "請擔任專業影片分析師，觀察此影片並為 AI 影片生成模型 (如 Sora) 撰寫英文提示詞 (Prompt)。包含：主角特徵、動作、環境、鏡頭運動與光影氛圍。"
        
        response = client.models.generate_content(model=target_model, contents=[video_file, prompt_instruction])
        
        client.files.delete(name=video_file.name)
        if os.path.exists("temp_ai_input.mp4"): os.remove("temp_ai_input.mp4")
        
        return response.text
    except Exception as e:
        return f"❌ AI 分析失敗: {str(e)}"

# ========================
# GUI Setup
# ========================
# 修改 CONFIG_FILE 定義
BASE_PATH = get_base_path()
CONFIG_FILE = os.path.join(BASE_PATH, "config.json")


def default_config():
    return {
        "api_key": "",             # YouTube API
        "gemini_key": "",          # Gemini API
        "keyword": "animal",
        "days": 7,
        "min_views": 100000,
        "min_subs": 0,
        "max_results": 30,
        "min_viral_score": 3000,
        "max_duration": 20  # 預設排除超過 20 秒的影片
    }

def load_config():
    default = default_config()
    if not os.path.exists(CONFIG_FILE): return default
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        user_cfg = json.load(f)
    for key, value in default.items():
        if key not in user_cfg: user_cfg[key] = value
    return user_cfg

def save_config(data):
    """ 儲存設定到絕對路徑，並加入錯誤捕捉 """
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # 如果因為權限問題無法存檔，跳出提示告知使用者
        messagebox.showerror("存檔失敗", f"無法儲存設定檔至：\n{CONFIG_FILE}\n錯誤訊息：{e}")

def resource_path(relative_path):
    """ 取得內置資源（如圖示）的暫存路徑 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

ICON_PATH = resource_path("icon.ico")

root = tk.Tk()
root.title("YouTube Shorts 趨勢與 AI 影片分析工具")
# 設定視窗圖示（若檔案存在則載入）
if os.path.exists(ICON_PATH):
    try:
        root.iconbitmap(ICON_PATH)
    except:
        pass
root.geometry("1000x800")

cfg = load_config()
api_key_var = tk.StringVar(value=cfg["api_key"])
gemini_key_var = tk.StringVar(value=cfg.get("gemini_key", ""))
keyword_var = tk.StringVar(value=cfg["keyword"])
days_var = tk.IntVar(value=cfg["days"])
min_views_var = tk.IntVar(value=cfg["min_views"])
min_subs_var = tk.IntVar(value=cfg["min_subs"])
max_results_var = tk.IntVar(value=cfg["max_results"])
min_viral_score_var = tk.DoubleVar(value=cfg["min_viral_score"])
max_duration_var = tk.IntVar(value=cfg.get("max_duration", 20))

current_results = []
selected_url = ""

# ========================
# Actions
# ========================
def start_ai_process(url):
    """ 核心 AI 啟動流程，支援不同來源的 URL """
    notebook.select(ai_tab)
    ai_text.delete("1.0", tk.END)
    ai_text.insert(tk.END, f"🚀 啟動分析：{url}\n")
    
    def worker():
        # 這裡調用您原始碼中定義的 ai_generate_prompt
        result = ai_generate_prompt(
            gemini_key_var.get().strip(), 
            url, 
            lambda msg: root.after(0, lambda: ai_text.insert(tk.END, f"> {msg}\n"))
        )
        root.after(0, lambda: ai_text.insert(tk.END, f"\n--- 分析結果 ---\n\n{result}"))

    import threading
    threading.Thread(target=worker, daemon=True).start()
    
def run_ai_analysis():
    global selected_url
    if not selected_url:
        messagebox.showwarning("提示", "請先從清單中右鍵點選一部影片。")
        return
    start_ai_process(selected_url)
    
    notebook.select(ai_tab)
    ai_text.delete("1.0", tk.END)
    ai_text.insert(tk.END, "🚀 啟動 AI 分析流程...\n")
    
    def worker():
        result = ai_generate_prompt(
            gemini_key_var.get().strip(), 
            selected_url, 
            lambda msg: root.after(0, lambda: ai_text.insert(tk.END, f"> {msg}\n"))
        )
        root.after(0, lambda: ai_text.insert(tk.END, f"\n--- 分析結果 ---\n\n{result}"))

    import threading
    threading.Thread(target=worker, daemon=True).start()

def copy_ai_result():
    content = ai_text.get("1.0", tk.END)
    pyperclip.copy(content)
    messagebox.showinfo("成功", "AI 結果已複製到剪貼簿")

# ========================
# UI Tabs
# ========================
notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

basic_tab = ttk.Frame(notebook)
adv_tab = ttk.Frame(notebook)
result_tab = ttk.Frame(notebook)
ai_tab = ttk.Frame(notebook)

notebook.add(basic_tab, text="基本設定")
notebook.add(adv_tab, text="進階與 API")
notebook.add(result_tab, text="分析結果")
notebook.add(ai_tab, text="AI Prompt 結果")

# --- Basic Tab ---
def labeled_entry(parent, label, var, row, help_text=None):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=5)
    ttk.Entry(parent, textvariable=var, width=40).grid(row=row, column=1, padx=10)
    if help_text: ttk.Label(parent, text=help_text, foreground="gray").grid(row=row, column=2, sticky="w")

labeled_entry(basic_tab, "關鍵字", keyword_var, 0)
labeled_entry(basic_tab, "搜尋天數", days_var, 1, "例如: 7 = 最近 7 天")
labeled_entry(basic_tab, "排除長度超過(秒)", max_duration_var, 2, "例如: 20 = 只找 20 秒內的影片")

# --- Adv Tab ---
labeled_entry(adv_tab, "YouTube API Key", api_key_var, 0, "到 Google Cloud 申請 YouTube Data API v3")
labeled_entry(adv_tab, "Gemini API Key", gemini_key_var, 1, "用於分析影片產生 Prompt")
labeled_entry(adv_tab, "最少觀看數", min_views_var, 2, "低於此數字會被過濾")
labeled_entry(adv_tab, "爆發指數門檻", min_viral_score_var, 3, "觀看數 ÷ 發布後小時（越高代表成長越快）")

# --- Result Tab ---
tree = ttk.Treeview(result_tab, columns=("title", "views", "duration","hours", "viral", "published", "url"), show="headings")
for col, head in zip(tree["columns"], ["標題", "觀看數", "總時長", "發布小時", "爆發指數", "發布時間"]):
    tree.heading(col, text=head)
tree.column("title", width=300)
tree.column("views", width=100)
tree.column("duration", width=80, anchor="center")
tree.column("hours", width=80, anchor="center")
tree.column("viral", width=100, anchor="center")
tree.column("published", width=150, anchor="center")
tree.column("url", width=0, stretch=tk.NO) # 關鍵：設為 0 且不延伸，URL 就會消失
tree.pack(fill="both", expand=True, padx=10, pady=10)

# 右鍵選單
context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="開啟影片 (瀏覽器)", command=lambda: webbrowser.open(selected_url))
context_menu.add_command(label="複製連結", command=lambda: pyperclip.copy(selected_url))
context_menu.add_separator()
context_menu.add_command(label="✨ 使用 AI 產生影片 Prompt", command=run_ai_analysis)

def show_context_menu(event):
    global selected_url
    item_id = tree.identify_row(event.y)
    if item_id:
        tree.selection_set(item_id)
        selected_url = tree.item(item_id, "values")[-1]
        context_menu.tk_popup(event.x_root, event.y_root)

tree.bind("<Button-3>", show_context_menu)

# --- AI Tab ---

# --- AI Tab 介面優化 ---
url_frame = ttk.Frame(ai_tab)
url_frame.pack(fill="x", padx=10, pady=5)

ttk.Label(url_frame, text="直接輸入 Shorts 網址:").pack(side="left")
manual_url_var = tk.StringVar()
url_entry = ttk.Entry(url_frame, textvariable=manual_url_var, width=50)
url_entry.pack(side="left", padx=5)

def run_manual_ai():
    url = manual_url_var.get().strip()
    if not url:
        messagebox.showwarning("提示", "請輸入有效的 YouTube URL")
        return
    # 呼叫現有的 AI 分析流程，但傳入手動輸入的 URL
    start_ai_process(url)

ttk.Button(url_frame, text="立即分析", command=run_manual_ai).pack(side="left")

# 原有的文字框
ai_text = tk.Text(ai_tab, wrap="word", font=("Microsoft JhengHei", 10))
ai_text.pack(fill="both", expand=True, padx=10, pady=10)
ttk.Button(ai_tab, text="複製分析結果", command=copy_ai_result).pack(pady=5)

# ========================
# Run Actions
# ========================
def run_search():
    save_config({
        "api_key": api_key_var.get().strip(),
        "gemini_key": gemini_key_var.get().strip(),
        "keyword": keyword_var.get(),
        "days": days_var.get(),
        "min_views": min_views_var.get(),
        "min_subs": min_subs_var.get(),
        "max_results": max_results_var.get(),
        "min_viral_score": min_viral_score_var.get(),
        "max_duration": max_duration_var.get()
    })
    tree.delete(*tree.get_children())
    try:
        results = fetch_trending_shorts(api_key_var.get(), keyword_var.get(), days_var.get(), min_views_var.get(), 0, max_results_var.get(), min_viral_score_var.get(), max_duration_var.get())
        for r in results:
            tree.insert("", "end", values=(r["title"], r["views"], r["duration"], r["hours"], r["viral_score"], r["published"], r["url"]))
        notebook.select(result_tab)
    except Exception as e:
        messagebox.showerror("錯誤", str(e))

btn_frame = ttk.Frame(root)
btn_frame.pack(fill="x", pady=10)
ttk.Button(btn_frame, text="開始搜尋分析", command=run_search).pack(side="right", padx=10)

root.after(1000, check_for_updates) # 程式啟動 1 秒後檢查更新
root.mainloop()
