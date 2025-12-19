【YouTube Shorts AI 分析工具 - Mac 版使用說明】

感謝使用本工具！由於 Mac 安全機制較嚴格，請依照以下步驟進行「第一次」的設定：

1. 檔案解壓縮
   將下載的壓縮檔解壓縮到一個你喜歡的資料夾（例如：桌面或下載項目）。

2. 賦予執行權限 (僅需執行一次)
   由於 Mac 預設不執行不明的指令檔，請開啟「終端機」(Terminal)，輸入以下指令並按 Enter：
   chmod +x 

   (注意：chmod +x 後面有一個空格，然後直接將「啟動工具.command」檔案拖進終端機視窗，路徑會自動帶入)

3. 啟動程式
   直接「按兩下」點擊「啟動工具.command」即可啟動。

4. 疑難排解 (FFmpeg)
   如果 AI 分析功能無法正常下載影片，代表你的 Mac 缺少 ffmpeg。
   請開啟終端機，貼入這行指令安裝：
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" && brew install ffmpeg

5. 右鍵功能
   在搜尋結果清單中，你可以使用「兩指點擊」或「Control + 左鍵」來開啟 AI 分析選單。

祝你使用愉快！
