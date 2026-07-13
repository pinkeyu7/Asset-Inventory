# 財富儀表板

把記帳 App 匯出的複式記帳資料，變成一個可視化的個人淨值儀表板 —— 五個由帳本資料驅動的畫面：**淨值趨勢、資產組成佔比、月度收支、年度收支總結、收入來源分析**（含各來源年度比較，固定配色），外加三頁靜態的**分析報告**（不動產投資報酬率、C 房賣出時機、FIRE 退休戰略；手寫論述、不接帳本計算，收在主頁籤列的「📄 報告」下拉選單裡，並支援一鍵匯出 Markdown）。以 Google Apps Script（Google Sheet 當資料庫、`HtmlService` 出網頁）打造，零伺服器成本。

## 架構

```
記帳 App 匯出 source.plist
        │  （可選前處理，見「資料前處理」一節）
        │    tools/reclassify.py  支出科目 26 → 14 合併
        │    tools/condense.py    瑣碎交易依 (科目×期間) 濃縮
        ▼
        │  tools/convert.py（附會計恆等式驗證）
        ▼
data/accounts.csv + data/transactions.csv
        │  匯入
        ▼
Google Sheet（Transactions / Accounts 兩個工作表）＝ 資料庫
        │  src/Code.gs 讀取 → src/Ledger.gs 計算借貸與各月餘額
        ▼
Web App（HtmlService + Google Charts）＝ 儀表板，前端採 MVVM 分層
```

### 前端 MVVM 架構

`index.html` 只是骨架，透過 GAS 模板 `<?!= include('資料夾/檔名') ?>` 組入各分層檔案。
分層檔按層放進三個資料夾（GAS 沒有真的資料夾，clasp 會把 `model/Core_Model.html` 推成名為 `model/Core_Model` 的檔，編輯器顯示成資料夾，`include('model/Core_Model')` 可正常取用）：

```text
src/model/       Core_Model + Model_*（各頁純計算）+ Importer
src/viewmodel/   Core_ViewModel + ViewModel_*
src/view/        Core_View + View_* + View_Styles
```

採「**依層再依頁**」拆分：每層一個核心檔（共用基礎）＋每個頁面一個檔（擴充該層）：

- **Model** — `Core_Model`（資料持有 + helper）＋ `Model_{Trend,Composition,Monthly,Yearly,Income}`（各頁純計算）。不碰 DOM/圖表。
- **ViewModel** — `Core_ViewModel`（observable + 共用狀態 + init 協調）＋ `ViewModel_{…}`（各頁狀態/命令/computed）。
- **View** — `Core_View`（呈現層工具、分頁/上傳/密碼、啟動流程、頁面註冊）＋ `View_{…}`（各頁 render/wire/reload）。
- **Styles** — `View_Styles.html`。

**頁面註冊**：每個 `View_XXX` 以 `App.View.registerPage({name, render, wire, beforeInit, reload})` 向核心註冊；
核心負責分頁切換、初次/重載時依序呼叫各頁 hook。新增一頁＝三層各加一個 `*_XXX.html` 檔並註冊，不必改核心。

**靜態頁例外（報告類）**：不動產投資報酬率、C 房賣出時機、FIRE 退休戰略這三頁是純論述、不接帳本計算，
不需要 Model/ViewModel，也沒有 render/wire——各以一個薄註冊檔（`view/View_{Realty,CTiming,Fire}.html`）
呼叫 `registerPage({name})` 納入分頁切換，並綁定「匯出 Markdown」按鈕（共用 `view/View_Report_Export.html` 的 DOM→Markdown 轉換）。
報告內容是純 markup 片段（`view/View_*_Report.html`），由 `index.html` 對應的 `<section class="report">` 以 `include()` 組入；
三頁共用 `View_Styles.html` 的 `.report` 樣式區塊，配色對應主題變數以支援深/淺色。主頁籤列上這三頁收進「📄 報告」下拉選單，
只留五個常看的即時儀表板在外層。

資料載入有兩條路：GAS 版走 `google.script.run.getDashboardData(密碼)`；本機預覽走 `window.PRELOADED_DATA`（由 `make_preview.js` 注入）。

本機也可**免部署預覽**：`tools/make_preview.js` 會用真實資料產生 `preview/index.html`。

## 記帳借貸規則（重要）

來源資料是標準複式記帳。經反推並以**會計恆等式**驗證的規則（見 `src/Ledger.gs`）：

- 每筆交易 `Account1` = 借方、`Account2` = 貸方；**當 Account1 是收入(I) 時借貸互換**。
- 帳戶類型取全名第一字元：`A` 資產、`L` 負債、`I` 收入、`E` 支出。
- 正確性保證：**Σ資產 − Σ負債 === Σ收入 − Σ支出**。兩條路徑都會把關：離線 `convert.py`
  每次執行都印出差額；網頁上傳時後端 `Ledger.verifyIdentity` 在寫入前先驗，**不通過就中止匯入、
  不覆寫既有資料**（主要用來擋「上傳解析錯位、帳戶前綴非 A/L/I/E」這類結構性壞檔）。

### 時區

plist 以 **UTC（`Z`）** 儲存日期，但本人在 **+8**。兩個產生「日期／月份」欄位的地方
（`tools/convert.py`、`src/model/Importer.html`）都會先把 UTC 轉成 +8 當地時間再取
`YYYY-MM-DD` / `YYYY-MM`，否則跨午夜的交易會被錯歸到前一天／前一月／前一年。
台灣無日光節約，採固定 +8 偏移。計算引擎 `Ledger.gs` 只吃 `Month` 字串欄，來源欄位正確即正確。

## 資料前處理（可選）

`import_data/source.plist` 可先經兩支獨立的 plist→plist 工具整理，再交給 `convert.py`。兩者皆
**不動原始檔**（輸出成新檔），且都內建**會計恆等式驗證**，確保處理前後淨值不變。都是純資料整理、
與部署流程無關，故未收進 `Makefile`，直接以 `python3` 執行。

### 1. 重分類 `tools/reclassify.py`（一次性）

把記帳 App 的 26 個支出(E)科目合併成 14 個（改名、金額加總，不動資產/負債/收入科目）。
科目對照表寫在腳本頂端的 `REMAP`／`NEW_ORDER`，可自行調整。

```bash
python3 tools/reclassify.py            # source.plist → source.reclassified.plist
```

> 完整性檢查：若交易或帳戶出現未列入 `REMAP` 的支出科目會直接中止。故**只能對「尚未重分類」的
> 檔案執行一次**；對已是 14 科目的檔案再跑會因找不到舊科目而報錯。

### 2. 濃縮 `tools/condense.py`（精簡歷史）

把指定支出科目的瑣碎交易，依 (Account1, Account2, 期間) 分組加總成一筆，壓縮多年累積的細碎紀錄。
借貸方向與金額總和皆保留，故各帳戶餘額與對應顆粒度的統計（年報／月趨勢）仍成立。兩種顆粒度：

```bash
# 2026 前逐年濃縮、2026 逐月濃縮（本專案的最終狀態）
python3 tools/condense.py 固定週期費 保險 日常生活 交通移動 健康醫療 進修教育 \
    --yearly-before 2026 --monthly 2026 \
    --src import_data/source.reclassified.plist \
    --out import_data/source.condensed.plist
```

`--yearly-before N` = N 年（不含）以前每『年』併一筆；`--monthly Y …` = 指定年份每『月』併一筆；
其餘交易原樣保留。彙總筆的 `Note1` 會標注「期間＋科目彙總（N 筆）」方便辨識。

### 3. 接回 `convert.py`

前處理後的 plist 不是預設來源，需以參數指到它（或自行覆蓋 `source.plist`，建議先備份）：

```bash
python3 tools/convert.py import_data/source.condensed.plist   # → data/*.csv
```

## 使用步驟

常用操作都收進 `Makefile`，直接 `make` 看清單：

```bash
make            # 列出所有指令
make setup      # 檢查 python3/node、安裝 clasp
make login      # clasp 登入（開瀏覽器授權）
make convert    # source.plist → data/*.csv（含恆等式檢查）
make preview    # 產生並開啟本機預覽（免部署）
make test       # 執行單元測試
make push       # 上傳 src/ 到 Apps Script
make release    # 測試→上傳→更新既有部署（版本描述自動帶 git commit）
```

### 1. 產生資料 CSV

```bash
make convert    # = python3 tools/convert.py
# 之後更新：把新的匯出檔覆蓋 import_data/source.plist，再 make convert 一次即可
```

### 2. 本機預覽（可選，建議先看過）

```bash
make preview    # = node tools/make_preview.js + 開啟 preview/index.html（macOS）
```

### 3. 部署到 Google Apps Script（clasp）

先 `make setup` 安裝 [clasp](https://github.com/google/clasp)（= `npm install -g @google/clasp`）。

1. **建立繫結試算表的專案**：`clasp create-script --type sheets --title "財富儀表板"`
   會一次建立「一張新試算表 + 繫結它的 Apps Script 專案」，並產生 `.clasp.json`。
   把 `.clasp.json` 的 `rootDir` 改成 `"src"`（clasp 產生的暫存資料夾可刪除）。
   可參考 `.clasp.json.example`。
2. **上傳程式**：`make login` 後 `make push`（= `clasp push --force`，上傳 `src/` 內的檔案）。
3. **匯入資料**：兩種方式擇一
   - **（推薦）部署後直接在網頁上傳** `source.plist`（見下方「更新資料」），連工作表都會自動建立。
   - 或先手動把 `data/transactions.csv`、`data/accounts.csv` 匯入試算表，
     工作表名稱需為 `Transactions`、`Accounts`。
4. **部署為 Web App**：`clasp create-deployment`（或在編輯器 `部署 → 新增部署 → 網頁應用程式`）。
   - 執行身分＝**部署者（你）**；存取權依需求設定（見下方「存取控制」）。
   - 之後更新：用 `make list-deploys` 查出 deployment ID，填進 `.clasp.json` 的
     `"deploymentId"` 欄位，往後 `make release` 即可重新部署到**同一網址**
     （會先跑測試，並把 git commit 寫進 GAS 版本描述，方便對回原始碼）。

### 存取控制與通關密碼

`appsscript.json` 的 `webapp.access` 決定誰能開啟頁面：

- `MYSELF`：只有你。最安全。
- `ANYONE_ANONYMOUS`：任何人有網址即可開啟（免登入）。

本專案採「**頁面公開、資料需通關密碼**」：`access` 設為 `ANYONE_ANONYMOUS`，
但後端 `getDashboardData` / `importData` 都要求正確密碼才回傳/寫入資料（**fail-closed**，
未設密碼或密碼錯誤一律拒絕），前端進入時先顯示密碼畫面。

**設定密碼**（務必先設，否則連你自己都看不到資料）：
Apps Script 編輯器 → `專案設定 ⚙️ → 指令碼屬性` → 新增屬性 `ACCESS_CODE` = 你的密碼。
（或執行 `Code.gs` 的 `setAccessCode()`，把其中的 `'change-me'` 先改成你的密碼。）
密碼只存在指令碼屬性，**不寫進程式碼、不進版控**；要改密碼或停權就改這個屬性值。

### 4. 更新資料

**最簡單：在網頁上傳**（部署後）
直接開啟網頁應用程式 → 點右上角「⬆️ 上傳 source.plist」→ 選檔。
瀏覽器會在前端解析 plist、送到後端寫入 `Transactions`/`Accounts` 工作表、
清快取並自動重繪，無需手動跑 `convert.py` 或匯入 CSV。

**或用離線流程**
覆蓋 `source.plist` → `make convert` → 重新匯入兩個工作表 → 在試算表選單
`資產儀表板 → 清除快取`（或等 6 小時快取自動過期）→ 重新整理網頁。

## 測試

借貸引擎 `src/Ledger.gs` 是純函式，以 Node 原生測試器覆蓋（無外部相依）：

```bash
make test            # = node --test（執行 tests/ledger.test.js）
```

鎖住反推的借貸規則（`debitCredit` 收入互換、`contribution` 借貸方向）、月份索引互逆、
`buildTimeSeries` 逐月累積與年度/月度收支，以及 `verifyIdentity` 會計恆等式；
若已產生 `data/transactions.csv`，會一併對真實資料驗證恆等式。

## 檔案

| 路徑 | 說明 |
|------|------|
| `Makefile` | 常用指令入口（`make` 列出：convert/preview/test/push/deploy…） |
| `import_data/source.plist` | 記帳 App 匯出的原始檔（不會被修改） |
| `tools/reclassify.py` | 前處理（可選）：支出科目 26→14 合併，plist→plist，含恆等式驗證 |
| `tools/condense.py` | 前處理（可選）：瑣碎交易依 (科目×期間) 濃縮，plist→plist，含恆等式驗證 |
| `tools/convert.py` | plist → CSV，含恆等式驗證 |
| `tools/make_preview.js` | 產生本機預覽 `preview/index.html` |
| `data/*.csv` | 匯入 Google Sheet 用的資料 |
| `src/Ledger.gs` | 借貸引擎：各月餘額、月度/年度收支、`verifyIdentity` 恆等式驗證（伺服器端純函式） |
| `tests/ledger.test.js` | `Ledger.gs` 單元測試（`node --test`） |
| `src/Code.gs` | Web App 進入點、`include()`、讀寫試算表、`importData`、通關密碼檢查、快取 |
| `src/index.html` | 前端骨架，以 `include()` 組入下列分層並呼叫 `App.View.boot()` |
| `src/model/Core_Model.html` · `src/model/Model_*.html` | Model 核心 + 各頁純計算（Trend/Composition/Monthly/Yearly/Income） |
| `src/model/Importer.html` | Model：解析 plist → 列陣列（與 `convert.py` 同結果） |
| `src/viewmodel/Core_ViewModel.html` · `src/viewmodel/ViewModel_*.html` | ViewModel 核心（observable/init）+ 各頁狀態命令 |
| `src/view/Core_View.html` · `src/view/View_*.html` | View 核心（工具/分頁/上傳/密碼/啟動）+ 各頁 render/wire |
| `src/view/View_{Realty,CTiming,Fire}.html` · `..._Report.html` | 三頁靜態報告（不動產報酬／C 房賣點／FIRE）：前者註冊分頁並綁匯出鈕，後者為報告內容（純 markup） |
| `src/view/View_Report_Export.html` | 報告頁共用的 DOM→Markdown 匯出器（`App.View.bindReportExport`） |
| `src/view/View_Styles.html` | 樣式（CSS，含報告頁共用的 `.report` 配色） |
| `src/appsscript.json` | GAS 專案設定 |
