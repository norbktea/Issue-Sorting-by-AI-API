"""
Issue Sorting by AI API — Driver IC / Tcon IC 客⼾回饋分類⼯具
版本：2.0 重構重點：
 - 非同步並⾏（asyncio + aiohttp）：同時處理多份檔案
 - 結構化輸出（Pydantic）：鎖死 JSON 格式，欄位永遠對⿑
 - AI ⾃動判斷 Issue 類別（不再 Python 寫死清單）
 - 四家 API 對等⽀援：OpenAI / Grok / Claude / Gemini
 - API Key 使⽤環境變數，不存純⽂字檔案
依賴安裝（第⼀次執⾏前）：
 pip install aiohttp pydantic tk pypdf extract-msg
"""
# ── 標準庫 ──────────────────────────────────────────────────────────────────
import asyncio
import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
from typing import Optional
# ── 第三⽅套件 ───────────────────────────────────────────────────────────────
try:
 import aiohttp
except ImportError:
 print("請先執⾏：pip install aiohttp")
 sys.exit(1)
try:
 from pydantic import BaseModel, Field
except ImportError:
 print("請先執⾏：pip install pydantic")
 sys.exit(1)
# ── PDF / MSG 解析（選配，缺少時改⽤純⽂字讀取）────────────────────────────
try:
 import pypdf
 HAS_PYPDF = True
except ImportError:
 HAS_PYPDF = False
try:
 import extract_msg
 HAS_MSG = True
except ImportError:
 HAS_MSG = False
# ════════════════════════════════════════════════════════════════════════════
# Pydantic 結構化輸出模型
# ─── 這就是「格式鎖死」的核⼼。AI 必須回傳符合此結構的 JSON。
# 欄位說明：
# customer : 客⼾名稱（Samsung / Sony / Hisense / TPV / 其他）
# issue_category: AI ⾃動判斷的 Issue 類型，不由 Python 寫死
# deadline : 客⼾要求回覆 / 解決的 Deadline（字串，無則填 None）
# root_cause : 初步原因推斷（AI 從內容摘要）
# summary : ⼀句話摘要（選填，⽅便 UI 顯⽰）
# ════════════════════════════════════════════════════════════════════════════
class IssueReport(BaseModel):
 customer: str = Field(description="客⼾名稱，例如 Samsung、Sony、Hisense、TPV 或 Unknown")
 issue_category: str = Field(description="Issue 類別，由 AI 根據內容⾃由判斷，例如：Driver IC Timing Failure、Tcon IC 通訊異常、Display 閃爍、Color Deviation、ESD 損傷、Backlight 異常、其他")
 deadline: Optional[str] = Field(default=None, description="客⼾要求的 deadline，無則為 null")
 root_cause: str = Field(description="初步原因推斷，100 字以內")
 summary: str = Field(description="⼀句話摘要，50 字以內")
# ════════════════════════════════════════════════════════════════════════════
# Prompt ⼯廠
# ════════════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """你是⼀名資深 Display IC ⼯程師，專精於 Driver IC 與 Tcon IC 的客⼾品質回饋分析。
你的任務是從客⼾提供的⽂件（可能是 email、PDF 報告、MSG 信件）中，擷取並結構化以下資訊：
1. 客⼾名稱（Samsung、Sony、Hisense、TPV 等⾯板客⼾）
2. Issue 類別 — 請根據內容⾃⾏判斷，不限於固定清單。常⾒類型包括：
 Driver IC：Timing Failure、Init 失敗、SPI 通訊異常、過熱、ESD 損傷、Gamma 異常
 Tcon IC：LVDS/eDP 信號異常、Dithering 問題、FRC 錯誤、Frame Sync 問題
 Display 整體：閃爍（Flicker）、Color Deviation、Mura、Backlight 異常、Panel 壓傷
 其他：RMA 退貨、Spec 疑問、PCBA 焊接不良
3. Deadline（客⼾要求回覆或解決的⽇期，若無則填 null）
4. 初步原因推斷（根據⽂字內容合理推斷，非臆測）
5. ⼀句話摘要
請只輸出 JSON，格式完全符合以下結構，不要輸出任何額外⽂字：
{
 "customer": "...",
 "issue_category": "...",
 "deadline": "...",
 "root_cause": "...",
 "summary": "..."
}"""
def build_user_prompt(text: str) -> str:
 return f"【⽂件內容】\n{text[:4000]}\n【請輸出 JSON 結果】"
# ════════════════════════════════════════════════════════════════════════════
# 各家 API 的非同步請求函式
# 設計原則：每⼀家都⽤ aiohttp，回傳 IssueReport 或拋出例外
# ════════════════════════════════════════════════════════════════════════════
async def call_openai_compatible(
 session: aiohttp.ClientSession,
 base_url: str,
 api_key: str,
 model: str,
 text: str,
) -> IssueReport:
 """
 OpenAI 相容格式 — 適⽤於 ChatGPT 和 Grok
 
 [非同步原理] ⽤ async/await 發送請求：
 - 發出請求後立刻「讓出控制權」，讓其他任務也能跑
 - 等 API 回應時不佔⽤ CPU，可同時處理其他檔案
 
 [Pydantic 原理] response_format={"type": "json_object"} 強制回傳 JSON，
 再⽤ IssueReport.model_validate() 驗證欄位是否完整正確
 """
 payload = {
 "model": model,
 "messages": [
 {"role": "system", "content": SYSTEM_PROMPT},
 {"role": "user", "content": build_user_prompt(text)},
 ],
 "temperature": 0.0,
 "response_format": {"type": "json_object"}, # 強制 JSON 輸出
 }
 headers = {
 "Content-Type": "application/json",
 "Authorization": f"Bearer {api_key}",
 }
 async with session.post(
 f"{base_url}/chat/completions",
 json=payload,
 headers=headers,
 timeout=aiohttp.ClientTimeout(total=30),
 ) as resp:
 resp.raise_for_status()
 data = await resp.json()
 raw_json = data["choices"][0]["message"]["content"]
 return IssueReport.model_validate(json.loads(raw_json))
async def call_claude(
 session: aiohttp.ClientSession,
 api_key: str,
 text: str,
) -> IssueReport:
 """
 Anthropic Claude — 使⽤ Messages API
 
 [Claude 無原⽣ JSON mode] 因此在 Prompt 明確要求只回 JSON，
 再⽤ Pydantic 驗證。效果等同 OpenAI 的 json_object 模式。
 """
 payload = {
 "model": "claude-opus-4-5",
 "max_tokens": 512,
 "system": SYSTEM_PROMPT,
 "messages": [
 {"role": "user", "content": build_user_prompt(text)},
 ],
 "temperature": 0.0,
 }
 headers = {
 "Content-Type": "application/json",
 "X-API-Key": api_key,
 "anthropic-version": "2023-06-01",
 }
 async with session.post(
 "https://api.anthropic.com/v1/messages",
 json=payload,
 headers=headers,
 timeout=aiohttp.ClientTimeout(total=30),
 ) as resp:
 resp.raise_for_status()
 data = await resp.json()
 raw_text = data["content"][0]["text"].strip()
 # 防禦：有時 Claude 會在 JSON 前後多輸出說明⽂字，嘗試擷取 {}
 start = raw_text.find("{")
 end = raw_text.rfind("}") + 1
 raw_json = raw_text[start:end]
 return IssueReport.model_validate(json.loads(raw_json))
async def call_gemini(
 session: aiohttp.ClientSession,
 api_key: str,
 text: str,
) -> IssueReport:
 """
 Google Gemini — 使⽤ generateContent API
 
 [Key 位置修正] 原版把 Key 放在 URL，有洩漏風險。
 本版改放 Header x-goog-api-key，更安全。
 [JSON mode] 使⽤ responseMimeType 強制 JSON 輸出。
 """
 payload = {
 "contents": [
 {
 "parts": [
 {"text": SYSTEM_PROMPT + "\n\n" + build_user_prompt(text)}
 ]
 }
 ],
 "generationConfig": {
 "temperature": 0.0,
 "responseMimeType": "application/json", # Gemini 原⽣ JSON mode
 },
 }
 headers = {
 "Content-Type": "application/json",
 "x-goog-api-key": api_key, # Key 放 Header，不放 URL
 }
 async with session.post(
 "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
 json=payload,
 headers=headers,
 timeout=aiohttp.ClientTimeout(total=30),
 ) as resp:
 resp.raise_for_status()
 data = await resp.json()
 raw_json = data["candidates"][0]["content"]["parts"][0]["text"]
 return IssueReport.model_validate(json.loads(raw_json))
# ════════════════════════════════════════════════════════════════════════════
# 統⼀入⼝：根據 provider 分派到對應函式
# ════════════════════════════════════════════════════════════════════════════
async def classify_issue(provider: str, text: str, api_key: str) -> IssueReport | str:
 """
 回傳 IssueReport（成功）或錯誤字串（失敗）
 
 [asyncio.gather ⽤法]
 外部可以這樣同時處理多個檔案：
 results = await asyncio.gather(
 classify_issue(provider, text1, key),
 classify_issue(provider, text2, key),
 classify_issue(provider, text3, key),
 return_exceptions=True
 )
 三個 API 請求會同時發出，總等待時間約等於最慢那⼀個，⽽非三倍。
 """
 async with aiohttp.ClientSession() as session:
 try:
 if provider == "ChatGPT":
 return await call_openai_compatible(
 session, "https://api.openai.com/v1", api_key, "gpt-4o-mini", text
 )
 elif provider == "Grok":
 return await call_openai_compatible(
 session, "https://api.x.ai/v1", api_key, "grok-2-1212", text
 )
 elif provider == "Claude":
 return await call_claude(session, api_key, text)
 elif provider == "Gemini":
 return await call_gemini(session, api_key, text)
 else:
 return " 未知的 AI 供應商"
 except aiohttp.ClientResponseError as e:
 if e.status == 429:
 return " QUOTA_EXCEEDED"
 return f" HTTP 錯誤 {e.status}: {e.message}"
 except json.JSONDecodeError:
 return " AI 回傳格式錯誤，無法解析 JSON"
 except Exception as e:
 return f" 系統錯誤: {e}"
# ════════════════════════════════════════════════════════════════════════════
# 檔案⽂字擷取
# ════════════════════════════════════════════════════════════════════════════
def extract_text(file_path: str) -> str:
 ext = os.path.splitext(file_path)[1].lower()
 if ext == ".pdf":
 if HAS_PYPDF:
 try:
 reader = pypdf.PdfReader(file_path)
 return "\n".join(page.extract_text() or "" for page in reader.pages)
 except Exception as e:
 return f"[PDF 解析失敗] {e}"
 else:
 # fallback：強制讀取，PDF ⼆進位通常包含部分可讀⽂字
 try:
 with open(file_path, "rb") as f:
 raw = f.read()
 return raw.decode("utf-8", errors="ignore")
 except Exception as e:
 return f"[PDF 讀取失敗] {e}"
 elif ext == ".msg":
 if HAS_MSG:
 try:
 msg = extract_msg.Message(file_path)
 parts = [
 f"Subject: {msg.subject or ''}",
 f"From: {msg.sender or ''}",
 f"Date: {msg.date or ''}",
 f"Body:\n{msg.body or ''}",
 ]
 return "\n".join(parts)
 except Exception as e:
 return f"[MSG 解析失敗] {e}"
 else:
 try:
 with open(file_path, "rb") as f:
 return f.read().decode("utf-8", errors="ignore")
 except Exception as e:
 return f"[MSG 讀取失敗] {e}"
 else:
 # 純⽂字類型（.txt, .eml 等）
 for enc in ["utf-8", "cp950", "latin-1"]:
 try:
 with open(file_path, "r", encoding=enc, errors="ignore") as f:
 return f.read()
 except Exception:
 continue
 return "[無法讀取此檔案]"
# ════════════════════════════════════════════════════════════════════════════
# API Key 管理 — 優先使⽤環境變數（比 config.txt 安全）
# ════════════════════════════════════════════════════════════════════════════
ENV_KEY_MAP = {
 "ChatGPT": "OPENAI_API_KEY",
 "Grok": "GROK_API_KEY",
 "Claude": "ANTHROPIC_API_KEY",
 "Gemini": "GEMINI_API_KEY",
}
def get_api_key(provider: str) -> tuple[str | None, str | None]:
 """
 依序嘗試：環境變數 → config.txt
 回傳 (key, error_message)
 """
 env_name = ENV_KEY_MAP.get(provider, "")
 key = os.environ.get(env_name, "").strip()
 if key:
 return key, None
 # Fallback：讀 config.txt（與程式同⽬錄）
 config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.txt")
 if os.path.exists(config_path):
 import configparser
 cfg = configparser.ConfigParser()
 cfg.read(config_path, encoding="utf-8")
 section = "API_SETTINGS"
 key_name = f"{provider.upper()}_API_KEY"
 if section in cfg and key_name in cfg[section]:
 key = cfg[section][key_name].strip()
 if key and "your" not in key and "請填入" not in key:
 return key, None
 return None, (
 f"找不到 {provider} 的 API Key。\n\n"
 f"請在系統環境變數中設定 {env_name}，\n"
 f"或在 config.txt 的 [API_SETTINGS] 加入 {provider.upper()}_API_KEY=..."
 )
# ════════════════════════════════════════════════════════════════════════════
# Tkinter UI
# ════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
 def __init__(self):
 super().__init__()
 self.title("Driver IC / Tcon IC Issue 分類器 v2.0")
 self.geometry("620x580")
 self.resizable(False, False)
 self.configure(bg="#1e2330")
 self._build_ui()
 def _build_ui(self):
 PAD = {"padx": 20, "pady": 6}
 # 標題
 tk.Label(
 self,
 text="Driver IC / Tcon IC Issue 分類器",
 font=("Arial", 15, "bold"),
 fg="#a8d8ff",
 bg="#1e2330",
 ).pack(pady=(20, 4))
 tk.Label(
 self,
 text="⽀援 PDF / MSG · AI ⾃動分析 · 非同步並⾏處理",
 font=("Arial", 9),
 fg="#7a8aaa",
 bg="#1e2330",
 ).pack(pady=(0, 14))
 # AI 選擇
 frm = tk.Frame(self, bg="#1e2330")
 frm.pack(**PAD)
 tk.Label(frm, text="AI 引擎：", font=("Arial", 11), fg="#c8d8f0", bg="#1e2330").pack(side=tk.LEFT)
 self.combo = ttk.Combobox(
 frm,
 values=["ChatGPT", "Grok", "Claude", "Gemini"],
 state="readonly",
 width=14,
 font=("Arial", 11),
 )
 self.combo.current(0)
 self.combo.pack(side=tk.LEFT, padx=8)
 # 選擇按鈕
 self.btn = tk.Button(
 self,
 text="選擇檔案並分析 (.pdf / .msg)",
 font=("Arial", 12, "bold"),
 bg="#2a7fff",
 fg="white",
 activebackground="#1a5fcc",
 relief=tk.FLAT,
 padx=16,
 pady=8,
 command=self._on_click,
 )
 self.btn.pack(pady=14)
 self.lbl_file = tk.Label(self, text="尚未選取檔案", font=("Arial", 10), fg="#7a8aaa", bg="#1e2330")
 self.lbl_file.pack()
 # 分隔線
 tk.Frame(self, height=1, bg="#2e3a50").pack(fill=tk.X, padx=20, pady=14)
 # 結果欄位
 fields = [
 ("客⼾", "lbl_customer"),
 ("Issue 類別", "lbl_category"),
 ("Deadline", "lbl_deadline"),
 ("初步原因", "lbl_rootcause"),
 ("摘要", "lbl_summary"),
 ]
 for label_text, attr in fields:
 row = tk.Frame(self, bg="#1e2330")
 row.pack(fill=tk.X, padx=24, pady=3)
 tk.Label(
 row,
 text=f"{label_text}：",
 font=("Arial", 10, "bold"),
 fg="#7fb8ff",
 bg="#1e2330",
 width=10,
 anchor="w",
 ).pack(side=tk.LEFT)
 lbl = tk.Label(
 row,
 text="—",
 font=("Arial", 10),
 fg="#d0ddf0",
 bg="#1e2330",
 anchor="w",
 wraplength=400,
 justify=tk.LEFT,
 )
 lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
 setattr(self, attr, lbl)
 # 狀態列
 self.lbl_status = tk.Label(
 self,
 text="就緒",
 font=("Arial", 10, "italic"),
 fg="#7a8aaa",
 bg="#1e2330",
 )
 self.lbl_status.pack(pady=(16, 4))
 def _set_status(self, text: str, color: str = "#7a8aaa"):
 self.lbl_status.config(text=text, fg=color)
 self.update()
 def _clear_result(self):
 for attr in ("lbl_customer", "lbl_category", "lbl_deadline", "lbl_rootcause", "lbl_summary"):
 getattr(self, attr).config(text="—")
 def _show_result(self, report: IssueReport):
 self.lbl_customer.config(text=report.customer)
 self.lbl_category.config(text=report.issue_category)
 self.lbl_deadline.config(text=report.deadline or "未提及")
 self.lbl_rootcause.config(text=report.root_cause)
 self.lbl_summary.config(text=report.summary)
 def _on_click(self):
 provider = self.combo.get()
 api_key, err = get_api_key(provider)
 if err:
 messagebox.showerror("API Key 錯誤", err)
 return
 file_path = filedialog.askopenfilename(
 title="選擇 Issue 檔案",
 filetypes=[("⽀援格式", "*.pdf *.msg"), ("All Files", "*.*")],
 )
 if not file_path:
 return
 self.lbl_file.config(text=f"已選取：{os.path.basename(file_path)}", fg="#a8d8ff")
 self._clear_result()
 self._set_status(f" {provider} 分析中…", "#f5a623")
 self.btn.config(state=tk.DISABLED)
 # asyncio 在 Tkinter 主執⾏緒中執⾏（避免 threading 複雜度）
 async def run():
 text = extract_text(file_path)
 if text.startswith("["): # 讀取失敗
 return text
 return await classify_issue(provider, text, api_key)
 result = asyncio.run(run()) # 單檔案版本，直接 run
 self.btn.config(state=tk.NORMAL)
 if isinstance(result, str):
 if result == " QUOTA_EXCEEDED":
 self._set_status("API 額度已耗盡", "red")
 self.btn.config(state=tk.DISABLED)
 messagebox.showerror("超額警告", f"{provider} 的額度已⽤完，已停⽌服務。")
 else:
 self._set_status(result, "red")
 messagebox.showerror("分析失敗", result)
 elif isinstance(result, IssueReport):
 self._show_result(result)
 self._set_status(" 分析完成", "#4caf50")
 else:
 self._set_status(" 未知錯誤", "red")
# ════════════════════════════════════════════════════════════════════════════
# 進入點
# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
 app = App()
 app.mainloop()
