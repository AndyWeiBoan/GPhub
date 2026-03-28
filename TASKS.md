# GPhub AI Enhancement Tasks

## 目標
為 GPhub 加入 AI 生成內容：
1. 每篇 item 加一段 10-30 字**中文短評**（由 Gemini 生成）
2. 首頁頂部加 **Weekly Digest 區塊** — AI 將本週熱點事件串連並分析

## 技術選擇
- **AI API**: Google Gemini 2.5 Flash（免費 tier）
- **SDK**: `google-genai`（官方新版，舊版 `google-generativeai` 已 deprecated）
- **觸發方式**: 爬蟲完成後自動預處理，結果存 DB，前端直接讀
- **生成策略**: 全部 items 都嘗試生成，從高評分開始，已生成過的跳過

---

## Task 列表

---

### Task 0: 取得並驗證 Gemini API Key

**說明**
在 Google AI Studio 取得免費 API Key，並在本地環境測試串接成功。

**步驟（需要 user 操作）**
1. 前往 https://aistudio.google.com/apikey
2. 用 Google 帳號登入
3. 點 "Create API key"
4. 複製 API key
5. 把 key 設入 `backend/.env`：`GEMINI_API_KEY=你的key`

**驗收標準**
- [ ] `backend/.env` 有 `GEMINI_API_KEY` 設定
- [ ] 執行測試腳本能成功呼叫 Gemini API 並得到回應
- [ ] 確認 free tier 限制：15 req/min、1500 req/day（2026年目前免費額度）

**測試手法**
```bash
cd backend && python -c "
import asyncio
from google import genai

async def test():
    import os
    from dotenv import load_dotenv
    load_dotenv('.env')
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        print('ERROR: GEMINI_API_KEY not set')
        return
    client = genai.Client(api_key=key)
    response = await client.aio.models.generate_content(
        model='gemini-2.5-flash',
        contents='用繁體中文說一句話'
    )
    print('SUCCESS:', response.text)

asyncio.run(test())
"
```

**狀態**: ✅ 完成 — API key 已設入 `backend/.env`，串接測試通過

---

### Task 1: 加入 GEMINI_API_KEY 環境變數設定

**說明**
在 backend config 加入 `GEMINI_API_KEY`，並更新 `.env.example`。

**驗收標準**
- [ ] `backend/app/config.py` 有 `gemini_api_key: str | None = None` 欄位
- [ ] `.env.example` 有 `GEMINI_API_KEY=` 範例
- [ ] 未設定時不會 crash，只是跳過 AI 生成步驟

**測試手法**
1. 不設定 `GEMINI_API_KEY`，啟動 backend → 確認啟動正常
2. 設定假 key，確認 config 讀得到值：`python -c "from app.config import settings; print(settings.gemini_api_key)"`

---

### Task 2: Schema 變更 — 加入 ai_comment 欄位與 weekly_digests 表

**說明**
- `items` 表新增 `ai_comment TEXT` 欄位（nullable）
- 新增 `weekly_digests` 表儲存週報事件串連

**weekly_digests schema**
```
id          UUID / TEXT  PK
week_label  TEXT         e.g. "2026-W13"
title       TEXT         熱點事件標題
analysis    TEXT         AI 生成的事件串連分析（100-200 字）
item_ids    TEXT         JSON array of item UUIDs
created_at  DATETIME
```

**驗收標準**
- [ ] SQLAlchemy ORM model `WeeklyDigest` 存在於 `models.py`
- [ ] `items` model 有 `ai_comment` 欄位
- [ ] SQLite 本地環境下，啟動 backend 後兩個表/欄位都自動建立（`create_all`）
- [ ] PostgreSQL migration SQL 檔案存在於 `migrations/`

**測試手法**
1. 本地啟動後用 sqlite3 檢查：
   ```bash
   sqlite3 backend/ai_digest.db ".schema items" | grep ai_comment
   sqlite3 backend/ai_digest.db ".schema weekly_digests"
   ```
2. 檢查 ORM model import 不報錯：
   ```bash
   cd backend && python -c "from app.models import WeeklyDigest, Item; print('OK')"
   ```

---

### Task 3: Gemini API 客戶端

**說明**
建立 `backend/app/summarizer/gemini.py`，封裝 Gemini 1.5 Flash API 呼叫。

**功能**
- `generate_comment(title, raw_content) -> str | None`：生成 10-30 字中文短評
- `generate_digest(events: list[dict]) -> str | None`：接收多篇 item 摘要，生成事件串連分析
- Rate limiting：每次呼叫間隔至少 4 秒（free tier: 15 req/min）
- 失敗時 log warning 並回傳 `None`，不 raise exception

**Prompt 設計**
- 短評 prompt：「你是 AI 新聞編輯。用 10-30 個繁體中文字，寫一句這篇文章的獨到短評，重點是它的影響或獨特性，不要重複標題。文章標題：{title}。摘要：{content}」
- 事件串連 prompt：「你是 AI 科技週報編輯。以下是本週相關的 {n} 篇報導摘要，請用 100-200 個繁體中文字分析這個事件的來龍去脈與影響。{summaries}」

**驗收標準**
- [ ] `gemini.py` 存在，可獨立 import
- [ ] 無 `GEMINI_API_KEY` 時，呼叫立即回傳 `None` 並 log warning
- [ ] 有效 key 時，`generate_comment` 回傳非空字串
- [ ] API 錯誤時不 crash，回傳 `None`

**測試手法**
1. 無 key 測試：
   ```bash
   cd backend && python -c "
   from app.summarizer.gemini import GeminiClient
   c = GeminiClient(api_key=None)
   print(c.generate_comment('test', 'test'))  # 應該印出 None
   "
   ```
2. 有真實 key 時手動測試一次 `generate_comment`，確認回傳中文字串

---

### Task 4: Comment Generator — 批次生成 ai_comment

**說明**
建立 `backend/app/summarizer/comment_generator.py`，對 DB 中尚未有 `ai_comment` 的 items 批次生成短評。

**邏輯**
1. 查詢 `ai_comment IS NULL` 的 items，依 `total_score DESC` 排序
2. 每次處理最多 `GEMINI_COMMENT_BATCH_SIZE`（預設 50）筆
3. 呼叫 `GeminiClient.generate_comment()`
4. 成功則寫回 DB；失敗則跳過（不標記，下次還會重試）
5. 每筆間隔 4 秒（rate limit）

**驗收標準**
- [ ] `comment_generator.py` 存在
- [ ] 執行後 DB 中有 `ai_comment` 非 NULL 的 items
- [ ] 已有 `ai_comment` 的 items 不會被重新呼叫 API
- [ ] 無 Gemini key 時，函式直接 return，不報錯

**測試手法**
1. 手動執行：
   ```bash
   cd backend && python -c "
   import asyncio
   from app.summarizer.comment_generator import run_comment_generation
   asyncio.run(run_comment_generation())
   "
   ```
2. 執行後查詢 DB：
   ```bash
   sqlite3 backend/ai_digest.db "SELECT title, ai_comment FROM items WHERE ai_comment IS NOT NULL LIMIT 5;"
   ```
3. 再次執行，確認 log 顯示「跳過已有 comment 的 items」

---

### Task 5: Digest Generator — 生成週報熱點事件串連

**說明**
建立 `backend/app/summarizer/digest_generator.py`，找出本週熱點，串連成事件分析。

**邏輯**
1. 取本週（週一到今天）所有 items，依 `total_score DESC` 取 top 50
2. 用既有的 `topics.py` 取得 topic clusters（或簡化：用 category 分群）
3. 每個 cluster 取 top 3-5 筆 items
4. 呼叫 `GeminiClient.generate_digest()` 生成事件分析
5. 取前 5 個最高分 clusters 存入 `weekly_digests` 表
6. 同一週已存在的 digest 先刪除再重建（冪等）

**驗收標準**
- [ ] `digest_generator.py` 存在
- [ ] 執行後 `weekly_digests` 表有本週資料
- [ ] 同一週重複執行不會累積重複資料
- [ ] 無 Gemini key 時，函式直接 return
- [ ] `item_ids` 欄位為合法 JSON array

**測試手法**
1. 手動執行：
   ```bash
   cd backend && python -c "
   import asyncio
   from app.summarizer.digest_generator import run_digest_generation
   asyncio.run(run_digest_generation())
   "
   ```
2. 查詢結果：
   ```bash
   sqlite3 backend/ai_digest.db "SELECT week_label, title, substr(analysis,1,100) FROM weekly_digests;"
   ```
3. 再次執行，確認筆數不增加（冪等）

---

### Task 6: 整合進爬蟲 Pipeline

**說明**
在 `scheduler/jobs.py` 的 `crawl_and_summarise()` 末尾，加入 comment 和 digest 生成步驟。

**邏輯**
```
crawl → OG enrichment → Pexels enrichment → Claude summary → Gemini comments → Gemini digest
```

**驗收標準**
- [ ] `jobs.py` 的 pipeline 最後有呼叫 `run_comment_generation()` 和 `run_digest_generation()`
- [ ] 無 Gemini key 時，pipeline 正常完成，不報錯
- [ ] Admin panel 的手動觸發 crawl 也會跑這兩步

**測試手法**
1. 從 Admin panel 手動觸發 crawl，觀察 backend log，確認兩個步驟都有執行
2. 無 `GEMINI_API_KEY` 環境變數時跑 pipeline，確認整體流程不中斷

---

### Task 7: Backend API — 新增 weekly_digests endpoint

**說明**
在 `api/routes.py` 新增 GET `/api/weekly-digest` endpoint。

**回應格式**
```json
{
  "week_label": "2026-W13",
  "digests": [
    {
      "title": "事件標題",
      "analysis": "AI 生成的事件分析...",
      "item_ids": ["uuid1", "uuid2"],
      "items": [{ "id": "...", "title": "...", "url": "...", "ai_comment": "..." }]
    }
  ]
}
```

**驗收標準**
- [ ] `GET /api/weekly-digest` 回傳 200
- [ ] 無資料時回傳空 `digests: []`
- [ ] `items` 欄位有對應的 item 資料（join 查詢）

**測試手法**
```bash
curl http://localhost:8000/api/weekly-digest | python -m json.tool
```

---

### Task 8: Frontend — Item 短評顯示

**說明**
在首頁的 item card 和 Browse 頁的 ItemRow / PreviewPanel 顯示 `ai_comment`。

**設計**
- 顯示位置：item card 標題下方
- 樣式：小字（`text-xs`）、灰色斜體、前綴「💬」或「AI：」
- 只有 `ai_comment` 有值才顯示，沒有就不佔位

**驗收標準**
- [ ] 首頁 item card 有短評顯示（有資料時）
- [ ] Browse 頁 ItemRow 有短評顯示
- [ ] PreviewPanel 有短評顯示
- [ ] 無短評時 UI 不留白、不出現空格

**測試手法**
1. 瀏覽器開 `http://localhost:3000`，確認有短評的 items 顯示短評
2. 手動在 DB 把某個 item 的 `ai_comment` 設為 NULL，重新整理確認不顯示

---

### Task 9: Frontend — 首頁 Weekly Digest 區塊

**說明**
在首頁頂部（現有 magazine grid 之前）加入 Weekly Digest 區塊。

**設計**
```
┌─────────────────────────────────────────────────────┐
│  🗞 本週 AI 熱點                        Week 13/2026 │
├─────────────────────────────────────────────────────┤
│  [事件1標題]                                         │
│  AI 分析文字...                                      │
│  相關報導：[標題1] [標題2] [標題3]                    │
├─────────────────────────────────────────────────────┤
│  [事件2標題]  │  [事件3標題]  │  [事件4標題]          │
└─────────────────────────────────────────────────────┘
```

**驗收標準**
- [ ] 首頁有 Weekly Digest 區塊
- [ ] 顯示週次標籤（如 "Week 13, 2026"）
- [ ] 最多顯示 5 個事件
- [ ] 每個事件有標題、AI 分析、相關報導連結
- [ ] 無資料時整個區塊不顯示
- [ ] RWD：手機版正常顯示

**測試手法**
1. 瀏覽器開 `http://localhost:3000`，確認區塊出現
2. 縮小視窗到手機尺寸，確認 RWD 正常
3. 把 `weekly_digests` 表清空，確認首頁不顯示該區塊

---

## 完成標準

所有 Task 完成後，驗收整體流程：

1. 手動觸發 crawl
2. 等待 pipeline 完成
3. 首頁顯示 Weekly Digest 區塊（有事件分析）
4. 各 item card 有中文短評
5. Browse 頁短評顯示正確
6. 無 Gemini key 時，整個系統仍正常運作（graceful degradation）

---

## 注意事項

- Gemini free tier 限制（gemini-2.5-flash）：20 requests/day（實測確認）
- 每次 comment/digest 生成間隔 2 秒（實際每次呼叫約 8-10 秒，不需要額外等太久）
- GEMINI_COMMENT_BATCH_SIZE 預設 50，但 free tier 每日 20 次，實務上每次 crawl 最多能跑 15-18 筆
- 短評內容不可重複標題，要有獨到觀點
- 所有 AI 生成內容都是**可選的**（nullable），系統不依賴它運作
