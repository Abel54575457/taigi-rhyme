# 台灣唸歌仔 AI創作工作台 (Taiwanese Rhyme & Songwriting AI Studio)

專為台語流行歌、民謠、七字仔、四句聯創作者設計的一站式 AI 寫歌與押韻輔助系統。整合台灣話 **十三大通押韻部規則** 與 **教育部《臺灣閩南語常用詞辭典》28,695 筆權威詞庫**，支援即時押韻檢測、字詞智慧替換、前後句互換調適、句型倒裝與 Gemini AI 靈感擴寫。

---

## 🌟 核心功能特色

### 1. ✍️ 寫歌工作台與即時押韻檢測 (Lyric Studio)
- **多行即時分析**：輸入台語歌詞（全漢字、全台羅、或漢羅合用），每打一個字即時偵測每句句尾字詞。
- **音節與韻部拆解**：自動解析聲母、韻母、聲調（1~8調、平聲/仄聲/入聲）。
- **色彩標註與統計看板**：
  - 13 大通押部專屬色彩徽章（如 `OPEN_A`, `NASAL_AN`, `COMPOUND_AI` 等）。
  - 狀態標籤：🟢 押主韻、🔵 偶句通押、🔴 出韻/待修。
  - 即時統計：整首押韻率 (%)、主押韻部、有效行數、出韻行數警示。
  - 內建經典範例：江蕙《家後》、茄子蛋《浪子回頭》、蕭煌奇《阿嬤的話》、傳統四句聯《望春風》。

### 2. 💡 AI 換字換句靈感助手 (Songwriting & Alternation Assistant)
- **🔤 尾字/尾詞智慧替換**：
  - 針對出韻行，保留原句前段文意，依據目標押韻部與情境（思念情感、人生歲月、自然景色、江湖志向等）推薦契合的台語押韻詞彙。
  - 提供漢字、台羅、詞性、教育部釋義與整句預覽，支援「一鍵套用進歌詞」。
- **🔄 前後句互換（改換上一句）**：
  - 解決填詞常見情境：「當前句寫得很好不想改，但與上句不合韻」，系統反向改寫上一句尾字來遷就本句，維持通押。
- **🔀 台語句型倒裝與加襯**：
  - 提供道地台語倒裝結構（如情感焦點前置、句末襯字收韻），增加旋律節奏感。
- **🎶 下句靈感接龍**：
  - 依當前句意境，自動生成押同韻且符合情境的承接對偶句，支援「一鍵插入下一句」。
- **🤖 Gemini AI 雲端深度詩意生成**：
  - 支援填入 Google Gemini API Key，呼叫高階大模型進行台語文言雅化潤飾與多段副歌延伸。

### 3. 📖 教育部辭典押韻反查寶典 (Rhyming Lexicon)
- **13 大通押部快速篩選**：點擊韻部標籤即可檢索該部所有收錄詞目。
- **多維度組合篩選**：
  - 字數：單字 (1字)、雙字詞 (2字)、三字詞 (3字)、四字成語 (4字)。
  - 聲調：第 1~8 調、平聲 (1, 5)、仄聲 (2, 3, 7)、入聲 (4, 8)。
  - 詞性：動詞、名詞、形容詞、副詞等。
  - 關鍵字搜尋：搜尋漢字、台羅拼音或中文釋義。
- **詞卡工具**：完整呈現詞目、台羅、詞性、聲調、義項解說，支援一鍵「複製」或「加進歌詞」。

### 4. 📚 十三大通押部體系指南 (Rhyme System Guide)
- 收錄 13 大通押大類（開尾韻 5 部、複元音 2 部、陽聲韻 3 部、塞音入聲 3 部）。
- 完整列出所屬全體韻母變體（Variants）與通押語音學說明。

---

## 🚀 快速啟動方式

### 方法一：Windows 一鍵雙擊啟動
在檔案總管中雙擊執行專案目錄下的：
👉 **`run_app.bat`**

瀏覽器將自動開啟：`http://127.0.0.1:8899`

### 方法二：終端機指令啟動
```powershell
python server.py
```
開啟瀏覽器前往：`http://127.0.0.1:8899`

---

## 📂 專案架構說明

```
h:/我的雲端硬碟/116年/AI專區/台語韻腳/
├── rhyme_groups.json      # 13 大通押韻部標準規則定義表
├── rhyme_helper.py        # 台羅拼音音節拆解、聲母韻母分離與押韻比對工具
├── build_dict_db.py       # 從教育部 kautian.ods 建立 SQLite 索引資料庫之建置腳本
├── taigi_dict.db          # 2.8 萬筆詞目、2 萬筆字音、近義詞與韻部索引 SQLite 資料庫
├── rhyme_service.py       # 核心服務層：歌詞分析、詞庫反查、換詞換句演算法、Gemini 連線
├── server.py              # Bottle Web API 伺服器
├── index.html             # 現代化單一頁面響應式寫歌工作台 (Tailwind CSS + Vanilla JS)
├── run_app.bat            # Windows 一鍵啟動腳本
└── README.md              # 系統說明文件
```

---

## 🎼 十三大通押部對照表

| 編號 | 韻部代碼 | 說明 | 包含台羅韻母 (Variants) |
| :---: | :--- | :--- | :--- |
| 1 | `OPEN_A` | A類開尾韻（口音、鼻化、介音通押） | a, ah, ann, annh, ia, iah, iann, iannh, ua, uah, uann, uannh |
| 2 | `OPEN_E` | E類開尾韻 | e, eh, enn, ennh, ue, ueh, uenn, uennh |
| 3 | `OPEN_I` | I類開尾韻 | i, ih, inn, innh |
| 4 | `OPEN_O` | O類開尾韻 | o, oh, oo, ooh, onn, onnh, io, ioh |
| 5 | `OPEN_U` | U類開尾韻 | u, uh, unnh |
| 6 | `COMPOUND_AU` | AU/IU類通押 | au, auh, aunn, aunnh, iau, iauh, iaunn, iu, iuh, iunn |
| 7 | `COMPOUND_AI` | AI/UI類通押 | ai, aih, ainn, uai, uaih, uainn, ui, uih, uinn |
| 8 | `NASAL_AN` | AN類陽聲通押（-m, -n, -ng） | an, am, ang, ian, iam, iang, uan, uang |
| 9 | `NASAL_EN` | IN/ENG類陽聲通押 | in, im, ing, en, eng (含擴充 un) |
| 10 | `NASAL_ON` | ONG/OM類陽聲通押 | ong, om, iong (含擴充 ng, m) |
| 11 | `STOP_AT` | AT類塞音入聲通押（-p, -t, -k） | at, ap, ak, iat, iap, iak, uat, uak |
| 12 | `STOP_ET` | IT/EK類塞音入聲通押 | it, ip, ik, ek (含擴充 ut) |
| 13 | `STOP_OK` | OK/OP類塞音入聲通押 | ok, op, iok |
