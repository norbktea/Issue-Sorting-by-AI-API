#####你可以教他一個 Notepad++ 的神技，不用切換到 CMD 也能跑程式：在 Notepad++ 按下 F5。在輸入框貼入這行：cmd /k python "$(FULL_CURRENT_PATH)"按下 「執行」。這會直接跳出黑視窗跑出結果，這就是「開發環境」的雛形！

import os
import sys
import json
import urllib.request
import urllib.error
import configparser

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

CONFIG_FILE = "config.txt"

# 各大 AI API 的標準網址
API_URLS = {
    "ChatGPT": "https://openai.com",
    "Grok": "https://x.ai",
    "Claude": "https://anthropic.com",
    "Gemini": "https://googleapis.com"
}

def get_api_config(provider):
    """從外部 config.txt 安全讀取指定 AI 的金鑰"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, CONFIG_FILE)
    
    if not os.path.exists(config_path):
        return None, f"❌ 找不到設定檔：{CONFIG_FILE}\n請在程式旁建立此檔案。"
        
    try:
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")
        
        section = "API_SETTINGS"
        key_name = f"{provider.upper()}_API_KEY"
        
        if section in config and key_name in config[section]:
            api_key = config[section][key_name].strip()
            if not api_key or "your" in api_key or "請填入" in api_key:
                return None, f"❌ {key_name} 內容為空或尚未修改，請檢查 config.txt。"
            return api_key, None
        else:
            return None, f"❌ config.txt 格式錯誤，必須包含 [{section}] 與 {key_name}。"
    except Exception as e:
        return None, f"❌ 讀取設定檔失敗: {e}"


def extract_text_pure_python(file_path):
    """100% 純 Python 讀取檔案（免套件）"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if len(content.strip()) < 10:
            with open(file_path, "r", encoding="cp950", errors="ignore") as f:
                content = f.read()
        return content
    except Exception as e:
        return f"[檔案讀取錯誤] {e}"


def build_payload_and_headers(provider, text, api_key):
    """根據不同的 AI 供應商，封裝對應的請求格式與 Header"""
    truncated_text = text[:3000]
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

    url = API_URLS[provider]

    if provider in ["ChatGPT", "Grok"]:
        # OpenAI 與 xAI Grok 的格式通用
        model = "gpt-4o-mini" if provider == "ChatGPT" else "grok-2-1212"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    elif provider == "Claude":
        # Anthropic Claude 專有格式
        payload = {
            "model": "claude-3-5-sonnet-latest",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0
        }
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "anthropic-version": "2023-06-01"
        }
    elif provider == "Gemini":
        # Google Gemini 專有格式，Key 帶在 URL 後方
        url = f"{url}?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0}
        }
        headers = {"Content-Type": "application/json"}

    return url, json.dumps(payload).encode("utf-8"), headers


def parse_ai_success_response(provider, res_body):
    """解析各家 AI 成功回傳的 JSON"""
    res_json = json.loads(res_body)
    if provider in ["ChatGPT", "Grok"]:
        return res_json["choices"][0]["message"]["content"].strip()
    elif provider == "Claude":
        return res_json["content"][0]["text"].strip()
    elif provider == "Gemini":
        return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
    return "📂 Unclassified / 其他未分類"


def classify_issue_via_multi_ai(provider, text, api_key):
    """核心請求：向指定 AI 發送請求，並嚴密攔截各大廠商的超支/額度用盡報錯"""
    url, data, headers = build_payload_and_headers(provider, text, api_key)
    
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = response.read().decode("utf-8")
            return parse_ai_success_response(provider, res_body)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            err_data = json.loads(error_body)
            
            # 🟢 [ChatGPT & Grok 攔截] 檢查 HTTP 429 且代碼包含 insufficient_quota
            if provider in ["ChatGPT", "Grok"]:
                err_code = err_data.get("error", {}).get("code", "")
                err_msg = err_data.get("error", {}).get("message", "")
                if "quota" in err_code or "quota" in err_msg or e.code == 429:
                    return "🛑 QUOTA_EXCEEDED"
                    
            # 🟢 [Claude 攔截] 檢查 Anthropic 的 rate_limit_error 與超額描述
            elif provider == "Claude":
                err_type = err_data.get("error", {}).get("type", "")
                err_msg = err_data.get("error", {}).get("message", "")
                if "rate_limit" in err_type or "quota" in err_msg or e.code == 429:
                    return "🛑 QUOTA_EXCEEDED"
                    
            # 🟢 [Gemini 攔截] 檢查 Google 的 RESOURCE_EXHAUSTED 狀態
            elif provider == "Gemini":
                err_status = err_data.get("error", {}).get("status", "")
                err_msg = err_data.get("error", {}).get("message", "")
                if "EXHAUSTED" in err_status or "quota" in err_msg or e.code == 429:
                    return "🛑 QUOTA_EXCEEDED"
        except:
            pass
        return f"❌ 網路請求失敗 (HTTP {e.code})"
    except urllib.error.URLError as e:
        return f"❌ 連線失敗，可能遭防火牆封鎖\n原因: {e}"
    except Exception as e:
        return f"❌ 系統錯誤: {e}"


def select_and_process_file():
    """按鈕點擊觸發邏輯"""
    provider = combo_provider.get() # 取得使用者在 UI 選取的 AI 廠商
    
    api_key, err = get_api_config(provider)
    if err:
        messagebox.showerror("設定錯誤", err)
        return

    file_path = filedialog.askopenfilename(
        title="請選擇要分類的檔案",
        filetypes=[("支援的檔案", "*.pdf *.msg"), ("All Files", "*.*")]
    )
    if not file_path:
        return

    lbl_file_path.config(text=f"已選取檔案：{os.path.basename(file_path)}")
    lbl_result.config(text=f"🤖 {provider} 正在安全分類中...", fg="orange")
    root.update()

    content = extract_text_pure_python(file_path)
    if "[檔案讀取錯誤]" in content:
        messagebox.showerror("解析失敗", content)
        lbl_result.config(text="解析失敗", fg="red")
        return

    # 執行 AI 分類
    category = classify_issue_via_multi_ai(provider, content, api_key)
    
    # 🟢 萬流歸宗：不論哪一家超支，一律當場鎖死 UI 按鈕！
    if category == "🛑 QUOTA_EXCEEDED":
        lbl_result.config(text="API 額度已耗盡，停止服務", fg="red")
        btn_select.config(state=tk.DISABLED)
        messagebox.showerror("費用超額警告", f"您的 {provider} 免費 Token 或預算額度已用完！\n系統已自動關閉分類按鈕，以防產生額外費用。")
    elif "❌" in category:
        lbl_result.config(text="分類失敗", fg="red")
        messagebox.showerror("AI 分類失敗", category)
    else:
        lbl_result.config(text=category, fg="green")


# --- UI 介面建立 ---
root = tk.Tk()
root.title("Issue Sorting by AI API (多雲防刷費版)")
root.geometry("500x360")
root.resizable(False, False)

lbl_title = tk.Label(root, text="多雲智慧 AI 語意分類器", font=("Arial", 16, "bold"))
lbl_title.pack(pady=15)

# 新增：下拉選單選取 AI 供應商
frame_provider = tk.Frame(root)
frame_provider.pack(pady=5)
lbl_choose = tk.Label(frame_provider, text="請選擇 AI 引擎：", font=("Arial", 10))
lbl_choose.pack(side=tk.LEFT)

combo_provider = ttk.Combobox(frame_provider, values=["ChatGPT", "Grok", "Claude", "Gemini"], state="readonly", width=15)
combo_provider.current(0) # 預設選 ChatGPT
combo_provider.pack(side=tk.LEFT)

# 檔案選擇按鈕
btn_select = tk.Button(root, text="選擇檔案 (.pdf / .msg)", command=select_and_process_file, font=("Arial", 12))
btn_select.pack(pady=15)

lbl_file_path = tk.Label(root, text="尚未選取任何檔案", font=("Arial", 10), fg="gray")
lbl_file_path.pack(pady=5)

lbl_res_title = tk.Label(root, text="【 AI 分類結果 】", font=("Arial", 12, "bold"))
lbl_res_title.pack(pady=(15, 5))

lbl_result = tk.Label(root, text="請先選取檔案", font=("Arial", 14), fg="blue")
lbl_result.pack()

root.mainloop()
