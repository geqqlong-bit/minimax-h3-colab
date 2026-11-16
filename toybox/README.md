# H3 Toybox

一個接在 ComfyUI 後面的 MiniMax H3 網頁前端（H3 Studio 改名重做，2026-10-30）。

啟動：`start_h3toybox.bat`（需要 ComfyUI 已在 8188 執行），開 http://127.0.0.1:8190

## 三種模式

| 模式 | H3 任務 | 條件節點 | 改寫用的指南 |
|---|---|---|---|
| 🧸 參考生成 | Ref2VA | `MiniMaxH3ReferenceToVideo`（圖 9／影片 3／聲音 3） | `guides/..._ref_en.md` |
| 🎞 頭尾格 | I2VA／FL2VA／L2VA（看放了幾張） | `MiniMaxH3ImageToVideo` | `guides/..._base_en.md` |
| ✏️ 純文字 | T2VA | `MiniMaxH3ImageToVideo`（不接圖） | `guides/..._base_en.md` |

- 改寫模型是 Ref2VA 訓練的，base 任務它常回六段式；`normalize_base()` 會把它收回三段式，並重建第一行的對齊句（那一行是固定格式）。
- 指南來源：<https://huggingface.co/MiniMaxAI/MiniMax-H3/tree/main/docs>

## 🧵 延伸影片（參考模式）

素材盤裡的影片可以勾「延伸這支影片」，這時它不是參考影片，而是要被接下去的原片：

1. ffmpeg 把原片最後 3 秒轉成 24fps、生成尺寸（`h3t_tail_*.mp4`）
2. `MiniMaxH3MotionContext`（NikoDemon80/ComfyUI-H3-Motion-Context）把尾巴 22 格釘進新片段開頭（氣鎖），接在語意橋之後、採樣器之前
3. 原片最後一格同時當成一張參考圖，告訴改寫模型「從這一格接下去」
4. 解碼後 `MiniMaxH3MotionContextTrim` 剪掉那 22 格，再用 ffmpeg 把原片接上新片段 → `outputs/<job>_full.mp4`

SelfLift 採樣器會把 `minimax_keyframes` 縮到低解析度階段，所以頭尾格與氣鎖都能直接接兩段採樣。

## 工作流改動（相對 WF.json）

- 拿掉只為預覽存在的 `MiniMaxChunkFeedForward`(401) 與 `ModelPreviewOverrideKJ`(329)，SigmaShift(333) 直接接 scheduler／sampler
- `VHS_VideoCombine` 換成內建 `CreateVideo` ＋ `SaveVideo`（存到 `output/H3Toybox/`）
- 需要的外掛：T8 audio（Semantic Bridge）、SelfLift、H3 Motion Context

## 進度與剩餘時間

伺服器用標準庫自己連 ComfyUI 的 websocket（不需要 websocket-client），送件時帶同一個 client_id，就收得到那個 prompt 的 executing／progress 事件。

- 階段：排隊 → 準備 → 低解析度採樣 → 高解析度採樣 → 解碼存檔 →（延伸）接回原片
- 預估：採樣時用「已跑完的步」的中位數秒數外推；高解析度步還沒開始時，用歷史的高／低步數比換算
- 每次跑完把各階段時間（依像素×幀數正規化）以移動平均寫進 `stats.json`，越用越準

## 提示詞改寫的三種來源（設定頁）

| 來源 | 說明 |
|---|---|
| 🧸 本地小模型（預設） | H3 官方 9B 改寫模型的 W4A8 量化版，在 ComfyUI 的 `TextGenerate` 裡跑 |
| 💎 Gemini | 填 API 金鑰；模型預設 `gemini-3.8-flash`，清單另有 `gemini-3.5-flash-lite`，也可以自己輸入；按「驗證」會列出這把金鑰可用的模型 |
| 🔌 OpenAI 相容端點 | 端點網址、金鑰（本機伺服器可留空）、模型；「驗證」送一個極短的 POST 確認端點活著，順便讀 `/models` |

- 三種來源吃的是同一份訊息（`rewrite_message()`：system＝官方指南，user＝文字與圖片交錯）；base 任務的回覆一律經過 `normalize_base()`。
- 金鑰只存在伺服器的 `config.json`，**不會傳回瀏覽器**（只回 `has_key`）；表單留空＝沿用、按「清除」才會刪。

## 產品廣告導演（豎屏）

在影片模式選擇「產品廣告｜豎屏快節奏・密集鉤子・反轉」，畫幅設為 **9:16**，並開啟「提示詞改寫」。可先按「改寫預覽」檢查內容，再生成。

- 適用抖音、TikTok、小紅書等手機短片：前 1 秒鉤子、約每 1–2 秒推進資訊，按片長安排有鋪墊的反轉，保留產品演示與結尾回收。
- 在描述中提供平台、目標觀眾、產品真實賣點、台詞語言與參考素材。例如：「小紅書，10 秒，9:16，向租房族展示 @圖片1 的桌面收納盒；用抽屜卡住開場，兩次有鋪墊的反轉，中文短句，不增加參考產品沒有的功能。」
- 規則只影響提示詞，不會自動改畫幅或採樣步數；「快速模式」是另一項生成設定。未開啟改寫時，普通影片生成不套用導演規則。目前短片 Agent 按鈕也不傳送此選項。
- 自訂內容在 `directional_skills/product_ad/SKILL.md`。伺服器合併內建規則與 `config.json` 的 `skills_dir`，保留外部導演；同名時優先使用內建版本。改規則後重新按「改寫預覽」以更新已快取的提示詞；增刪選項後重新整理頁面。
- 此 fork 的 README 中 Toybox 按鈕與 `H3_Toybox.ipynb` 安裝來源均指向 `geqqlong-bit/minimax-h3-colab`。在 Colab 更新程式後重跑 ③ 啟動伺服器；無須搬動 T8 的導演目錄。

## ⚡ 快速模式（預設開）

SelfLift 兩段採樣從 12 步（低 6＋高 6）降到 8 步（低 4＋高 4）。步數設定在 `config.json` 的 `steps`。

## 🎙 用自己的聲音配音（IndexTTS2）

單支影片現在可上傳照片與一段自己的聲音，再填入要說的完整台詞。流程為 **H3 生成原片 → 釋放 H3 顯存 → IndexTTS2 克隆配音 → Demucs 分離原片人聲 → 新配音與背景音混合**。原片一直保留，配音失敗也可播放、下載原片。

### Colab 使用

1. 從此 fork 開啟最新版 `H3_Toybox.ipynb`，執行 ①、②，再執行獨立的 **②-b「下載 IndexTTS2 聲音克隆模型＋Demucs 人聲分離模型」**（`INSTALL_VOICE_CLONE` 預設勾選），最後執行／重跑 ③ 並重新整理網頁。已下載 H3 的使用者只需執行 ②-b、③，不必重抓 H3。③ 會識別安裝成功標記；若不執行 ②-b，仍可用原有 H3 功能。測試尚未合併的 PR 時，在 ① 將 `TOYBOX_REPO` 設為 PR 的 fork（例如 `Eleven1111/minimax-h3-colab`），`TOYBOX_REF` 設為 PR 分支；預設來源為本 fork 的 `main`。
2. 在影片頁上傳人物照並加入參考（或設為首格），勾選「用我的聲音配音」，透過其專用按鈕上傳 **3–30 秒清晰單人錄音**。聲音參考不會自動加入 H3 的素材盤。
3. 在「要說的台詞」填寫短句，再設定影片秒數。改寫預覽會把這段台詞作為唯一對白；克隆配音也使用同一段文字。
4. 生成完成後，結果卡可切換「我的聲音」與「原始影片」。加入素材庫時採用克隆配音版。

模型使用官方 [IndexTTS2 v2.0.0](https://github.com/index-tts/index-tts/tree/v2.0.0) 與 [IndexTeam/IndexTTS-2](https://huggingface.co/IndexTeam/IndexTTS-2)，代碼及主要權重固定 revision，未改用 IndexTTS 2.5。安裝器用獨立 Python 3.10、上游鎖檔與 CUDA 12.8 PyTorch，保留 ComfyUI 的 CUDA 13 環境，並在隔離環境安裝 Demucs 4.0.1、快取 `htdemucs`。需預留額外數 GB 磁碟與下載時間；IndexTTS 輔助模型仍可能在首次配音時下載。Demucs 使用 CPU，會增加處理時間。

### 範圍與限制

- 目前處理單一說話者的單支影片，支援參考生成、首尾格、純文字；不處理短片 Agent、多角色、延伸影片或自動語音識別。
- 保留的是 Demucs 分離出的非人聲背景，可能有殘留人聲或部分音效損失；不保證與原片背景逐樣本一致。
- 這是生成後重新配音，沒有新增對口型模型。配音從片頭開始，沒有逐句對齊原人聲的停頓；畫面口型、發音時刻與語氣不保證同步。
- 配音短於影片時補靜音，背景音繼續播放；略長時最多加速 1.25 倍；再長就顯示失敗並保留原片，不截斷台詞。
- 同一 Toybox 的 GPU 提交與配音互斥；已有 Comfy 工作先完成，再卸載 H3 並等待顯存釋放。配音時避免其他客戶端直接向 ComfyUI 提交工作。
- 聲音錄音作為素材存於原有 `library/`；若啟用 `SAVE_TO_DRIVE`，會隨素材存到 Google Drive。生成過程中的臨時錄音、分離音軌會清理。只上傳自己或已獲授權使用的聲音。

本機 Linux 也可執行 `python tools/install_indextts2.py --root /path/to/indextts2`，將產生的 `toybox_voice_config.json` 內容合併到 Toybox `config.json` 的 `voice_clone` 欄位後重啟。此安裝器不支援 macOS；目前尚未完成真實 Colab GPU 端到端驗證。

### 開發驗證

`python3 -m unittest discover -s toybox/tests -v`。媒體整合測試使用本機 ffmpeg/ffprobe 和合成測試音，檢查保留畫面、混入背景及新配音、時長、錯誤回退與臨時檔清理；不代表真實 IndexTTS 聲音相似度或 Demucs 分離品質已驗證。

## 📁 素材庫資料夾

素材可以拖進資料夾整理；拖到「🧸 全部素材」就移出來。資料夾只有一層，存在 `library/folders.json`，素材的 `folder` 欄位指向它。刪資料夾不會刪素材，素材會回到最外層。在資料夾裡上傳，或從生成結果「加入素材庫」，都會直接放進目前的資料夾。

## 💾 資料放在哪裡

使用者做出來的東西都放在 `H3TOYBOX_DATA`（沒設就是程式資料夾本身）：`library/`（含 `folders.json`）、`outputs/`、`jobs.json`、`stats.json`、`config.json`。
API 金鑰另外存在 `H3TOYBOX_SECRETS`（預設 `DATA/secrets.json`），不寫進 `config.json`。
啟動時 `restore_inputs()` 會把素材庫裡、但 ComfyUI input 資料夾缺的檔案補回去（新的執行階段 input 是空的）。

Colab 版 ③ 預設 `SAVE_TO_DRIVE`：DATA＝「我的雲端硬碟/H3Toybox」，ComfyUI 的 `output/H3Toybox` 也連結到那裡的 `videos/`；
`SAVE_API_KEYS` 預設不勾，金鑰只放在執行階段的暫存空間。

## 已知

- 延伸接點後約第 2 格有一格幾乎重複（幀差 1.5，正常約 19），播放時可能有 1/24 秒的頓點，尚未查明是哪一側。

## Colab

repo 根目錄的 `H3_Toybox.ipynb`：① 安裝 → ② 下載約 50 GB → ③ 啟動並用 Colab 內建代理開網頁。
Colab 版的 `config.json` 由 ③ 寫入（`free_after_rewrite: true`：改寫完就卸載 9B 模型，避免和 H3 模型同時佔記憶體）。
