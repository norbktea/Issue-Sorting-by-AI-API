#####你可以教他一個 Notepad++ 的神技，不用切換到 CMD 也能跑程式：在 Notepad++ 按下 F5。在輸入框貼入這行：cmd /k python "$(FULL_CURRENT_PATH)"按下 「執行」。這會直接跳出黑視窗跑出結果，這就是「開發環境」的雛形！


import os
import sys
import json
import urllib.request
import urllib.error
import configparser  # 內建讀取設定檔的套件，免安裝

import tkinter as tk
from tkinter import filedialog, messagebox

# 定義金鑰檔案的名稱
CONFIG_FILE = "config.txt"
API_URL = "https://openai.com"

def get_api_key():
    """
    從外部的 config.txt 檔案中安全讀取金鑰，避免直接寫在程式碼中。
    """
    # 取得目前程式執行所在的資料夾路徑，確保讀取正確位置
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, CONFIG_FILE)
    
    if not os.path.exists(config_path):
        return f"❌ 找不到設定檔：{CONFIG_FILE}\n請在程式旁建立此檔案並設定金鑰。"
        
    try:
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")
        
        # 檢查是否有對應的設定區塊與標籤
        if "API_SETTINGS" in config and "OPENAI_API_KEY" in config["API_SETTINGS"]:
            api_key = config["API_SETTINGS"]["OPENAI_API_KEY"].strip()
            if not api_key or "actual-api-key" in api_key:
                return "❌ 金鑰內容為空或尚未修改，請檢查 config.txt 檔案。"
            return api_key
        else:
            return f"❌ {CONFIG_FILE} 內格式錯誤，必須包含 [API_SETTINGS] 與 OPENAI_API_KEY。"
    except Exception as e:
        return f"❌ 讀取設定檔失敗: {e}"


def extract_text_pure_python(file_path):
    """100% 純 Python 讀取檔案"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if len(content.strip()) < 10:
            with open(file_path, "r", encoding="cp950", errors="ignore") as f:
                content = f.read()
        return content
    except Exception as e:
        return f"[檔案讀取錯誤] {e}"


def classify_issue_via_ai(text, api_key):
    """透過外部金鑰進行 AI 語意分類"""
    # 限制字數，避免 Token 超量
    truncated_text = text[:3000] 

    # 提示詞 (Prompt) 
    prompt = (
        "你是一個 IT 系統的 Issue 分類專家。請仔細閱讀以下由 PDF 或 MSG 檔案中提取出來的文字內容，"
        "並嚴格從以下四個類別中選擇一個最符合的分類填入：\n"
        "1. 🐛 Bug / 程式錯誤\n"
        "2. 💡 Feature Request / 新功能需求\n"
        "3. 💰 Billing / 財務帳務\n"
        "4. 📂 Unclassified / 其他未分類\n\n"
        "請直接回傳該分類的完整名稱即可（例如：'🐛 Bug / 程式錯誤'），不需要任何額外的解釋或前言。\n\n"
        f"【檔案內容開始】\n{truncated_text}\n【檔案內容結束】"
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            return res_json["choices"]["message"]["content"].strip()

    except urllib.error.URLError as e:
        return f"❌ 網路連線失敗 (可能是公司防火牆封鎖)\n詳細原因: {e}"
    except Exception as e:
        return f"❌ AI 解析發生錯誤: {e}"


def select_and_process_file():
    # 每次點擊執行時才讀取金鑰，確保即時性與資安
    api_key = get_api_key()
    if api_key.startswith("❌"):
        messagebox.showerror("資安與設定錯誤", api_key)
        return

    file_path = filedialog.askopenfilename(
        title="請選擇要分類的檔案",
        filetypes=[("支援的檔案", "*.pdf *.msg"), ("All Files", "*.*")]
    )

    if not file_path:
        return

    lbl_file_path.config(text=f"已選取檔案：{os.path.basename(file_path)}")
    lbl_result.config(text="🤖 AI 正在安全地讀取並分類中...", fg="orange")
    root.update()

    content = extract_text_pure_python(file_path)

    if "[檔案讀取錯誤]" in content:
        messagebox.showerror("解析失敗", content)
        lbl_result.config(text="解析失敗", fg="red")
        return

    # 將安全讀取到的金鑰帶入函式
    category = classify_issue_via_ai(content, api_key)
    
    if "❌" in category:
        lbl_result.config(text="分類失敗", fg="red")
        messagebox.showerror("AI 分類失敗", category)
    else:
        lbl_result.config(text=category, fg="green")


# --- UI 介面建立 ---
root = tk.Tk()
root.title("Issue 自動分類工具 (AI 資安強化版)")
root.geometry("500x300")
root.resizable(False, False)

lbl_title = tk.Label(root, text="AI 語意理解分類器", font=("Arial", 16, "bold"))
lbl_title.pack(pady=20)

btn_select = tk.Button(root, text="選擇檔案 (.pdf / .msg)", command=select_and_process_file, font=("Arial", 12))
btn_select.pack(pady=10)

lbl_file_path = tk.Label(root, text="尚未選取任何檔案", font=("Arial", 10), fg="gray")
lbl_file_path.pack(pady=5)

lbl_res_title = tk.Label(root, text="【 AI 分類結果 】", font=("Arial", 12, "bold"))
lbl_res_title.pack(pady=(20, 5))

lbl_result = tk.Label(root, text="請先選取檔案", font=("Arial", 14), fg="blue")
lbl_result.pack()

root.mainloop()
