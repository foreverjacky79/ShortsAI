import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
import threading
import pandas as pd
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from google import genai
import yt_dlp
import pyperclip
import webbrowser

# --- 相容性處理：UTC 修正 ---
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc

def get_base_path():
    """ 取得程式執行時的真實路徑 (相容 .exe 與 .py) """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def resource_path(relative_path):
    """ 取得內部資源路徑 (如圖示) """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

BASE_PATH = get_base_path()
CONFIG_FILE = os.path.join(BASE_PATH, "config.json")
ICON_PATH = resource_path("icon.ico")

# --- 設定存取邏輯 ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def save_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showerror("存檔失敗", f"無法儲存設定：{e}")

# --- 核心 AI 分析邏輯 ---
def ai_generate_prompt(gemini_api_key, video_url, progress_callback):
    try:
        progress_callback("正在下載影片片段...")
        
        # yt-dlp 設定：不再強制指向 _MEIPASS，讓它搜尋系統環境或同目錄
        ydl_opts = {
            'format': 'best[ext=mp4]/tiny',
            'outtmpl': 'temp_ai_input.mp4',
            'overwrites': True,
            'quiet': True,
            'no_warnings': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
            
        progress_callback("影片下載完成，正在上傳至 Gemini...")
        client = genai.Client(api_key=gemini_api_key)
        
        with open("temp_ai_input.mp4", "rb") as f:
            video_file = client.files.upload(file=f)
            
        progress_callback("AI 正在解析影片內容，請稍候...")
        prompt = """
        請分析這段 YouTube Shorts 影片，並生成一段專業的 AI 影片生成提示詞 (Video Prompt)。
        包含：1. 畫面構圖 2. 主角動作 3. 光影與氛圍 4. 運鏡方式。
        請以繁體中文回答。
        """
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[video_file, prompt]
        )
        
        # 清理暫存檔
        if os.path.exists("temp_ai_input.mp4"):
            os.remove("temp_ai_input.mp4")
            
        return response.text
    except Exception as e:
        return f"❌ 分析失敗: {str(e)}"

# --- GUI 介面建構 ---
root = tk.Tk()
root.title("Shorts 趨勢分析與 AI 助手")
root.geometry("900x700")

# 設定視窗圖示
if os.path.exists(ICON_PATH):
    try: root.iconbitmap(ICON_PATH)
    except: pass

config = load_config()

# 分頁系統
notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

basic_tab = ttk.Frame(notebook)
adv_tab = ttk.Frame(notebook)
ai_tab = ttk.Frame(notebook)

notebook.add(basic_tab, text="基本搜尋")
notebook.add(ai_tab, text="AI Prompt 分析")
notebook.add(adv_tab, text="進階與 API")

# --- [AI Tab] 手動輸入與結果顯示 ---
ai_manual_frame = ttk.LabelFrame(ai_tab, text="手動分析網址")
ai_manual_frame.pack(fill="x", padx=10, pady=10)

manual_url_var = tk.StringVar()
ttk.Entry(ai_manual_frame, textvariable=manual_url_var, width=60).pack(side="left", padx=5, pady=5)

def start_ai_process(url):
    """ 核心啟動分析流程 """
    if not url: return
    notebook.select(ai_tab)
    ai_text.delete("1.0", tk.END)
    ai_text.insert(tk.END, f"🚀 準備分析網址: {url}\n")
    
    key = gemini_key_var.get().strip()
    if not key:
        messagebox.showerror("錯誤", "請先到進階設定填寫 Gemini API Key")
        return

    def worker():
        res = ai_generate_prompt(key, url, lambda m: root.after(0, lambda: ai_text.insert(tk.END, f"> {m}\n")))
        root.after(0, lambda: ai_text.insert(tk.END, f"\n【分析結果】\n\n{res}"))
    
    threading.Thread(target=worker, daemon=True).start()

ttk.Button(ai_manual_frame, text="立即分析", command=lambda: start_ai_process(manual_url_var.get().strip())).pack(side="left", padx=5)

ai_text = tk.Text(ai_tab, font=("Microsoft JhengHei", 10), padx=10, pady=10)
ai_text.pack(fill="both", expand=True, padx=10, pady=5)

ttk.Button(ai_tab, text="複製分析結果", command=lambda: pyperclip.copy(ai_text.get("1.0", tk.END))).pack(pady=5)

# --- 其餘介面 (API 設定與搜尋) 略，請保持您原始碼中的 UI 佈局 ---
# (此處省略部分重複的 UI 代碼以節省篇幅，但請確保已加入 Button-2/3 綁定)

# --- 搜尋結果右鍵綁定 ---
def show_context_menu(event):
    item_id = tree.identify_row(event.y)
    if item_id:
        tree.selection_set(item_id)
        context_menu.post(event.x_root, event.y_root)

# 在建立 Treeview (tree) 後加入：
# tree.bind("<Button-2>", show_context_menu) # Mac
# tree.bind("<Button-3>", show_context_menu) # Windows
# tree.bind("<Control-Button-1>", show_context_menu) # Mac Ctrl+Click

# --- [API 變數定義範例] ---
gemini_key_var = tk.StringVar(value=config.get("gemini_key", ""))
# ... 保持其他 API 變數定義 ...

root.mainloop()