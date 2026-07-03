# 個人資產變化紀錄

把記帳 App 匯出的複式記帳資料，變成一個可視化的個人淨值儀表板 —— 五個畫面：**淨值趨勢、資產組成佔比、月度收支、年度收支總結、收入來源分析**（含各來源年度比較，固定配色）。以 Google Apps Script（Google Sheet 當資料庫、`HtmlService` 出網頁）打造，零伺服器成本。

## 架構

```
記帳 App 匯出 source.plist
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

`index.html` 只是骨架，透過 GAS 模板 `<?!= include('檔名') ?>` 組入各分層檔案：

- **Model**（`Model.html`）— 領域資料與純計算（KPI、趨勢序列、資產組成…），不碰 DOM/圖表。
- **ViewModel**（`ViewModel.html`）— 畫面狀態 + 命令 + 可觀察通知；使用者操作進來、更新狀態後 emit 事件。
- **View**（`View.html`）— 只綁 DOM、畫 Google Charts、把操作轉發給 ViewModel，訂閱其事件重繪。
- **Styles**（`View_Styles.html`）— 樣式。

資料載入有兩條路：GAS 版走 `google.script.run.getDashboardData()`；本機預覽走 `window.PRELOADED_DATA`（由 `make_preview.js` 注入）。

本機也可**免部署預覽**：`tools/make_preview.js` 會用真實資料產生 `preview/index.html`。

## 記帳借貸規則（重要）

來源資料是標準複式記帳。經反推並以**會計恆等式**驗證的規則（見 `src/Ledger.gs`）：

- 每筆交易 `Account1` = 借方、`Account2` = 貸方；**當 Account1 是收入(I) 時借貸互換**。
- 帳戶類型取全名第一字元：`A` 資產、`L` 負債、`I` 收入、`E` 支出。
- 正確性保證：**Σ資產 − Σ負債 === Σ收入 − Σ支出**（`convert.py` 每次執行都會檢查，差額應為 0）。

## 使用步驟

### 1. 產生資料 CSV

```bash
python3 tools/convert.py
# 之後更新：把新的匯出檔覆蓋 import_data/source.plist，再跑一次即可
```

### 2. 本機預覽（可選，建議先看過）

```bash
node tools/make_preview.js
open preview/index.html          # macOS
```

### 3. 部署到 Google Apps Script（clasp）

需先安裝 [clasp](https://github.com/google/clasp)：`npm install -g @google/clasp`

1. **建立繫結試算表的專案**：`clasp create-script --type sheets --title "個人資產變化紀錄"`
   會一次建立「一張新試算表 + 繫結它的 Apps Script 專案」，並產生 `.clasp.json`。
   把 `.clasp.json` 的 `rootDir` 改成 `"src"`（clasp 產生的暫存資料夾可刪除）。
2. **上傳程式**：`clasp login` 後 `clasp push --force`（上傳 `src/` 內的檔案）。
3. **匯入資料**：兩種方式擇一
   - **（推薦）部署後直接在網頁上傳** `source.plist`（見下方「更新資料」），連工作表都會自動建立。
   - 或先手動把 `data/transactions.csv`、`data/accounts.csv` 匯入試算表，
     工作表名稱需為 `Transactions`、`Accounts`。
4. **部署為 Web App**：`clasp create-deployment`（或在編輯器 `部署 → 新增部署 → 網頁應用程式`）。
   - 執行身分＝**部署者（你）**；存取權依需求設定（見下方「存取控制」）。
   - 更新後用 `clasp update-deployment <deploymentId>` 重新部署到同一網址。

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
覆蓋 `source.plist` → 跑 `convert.py` → 重新匯入兩個工作表 → 在試算表選單
`資產儀表板 → 清除快取`（或等 6 小時快取自動過期）→ 重新整理網頁。

## 檔案

| 路徑 | 說明 |
|------|------|
| `import_data/source.plist` | 記帳 App 匯出的原始檔（不會被修改） |
| `tools/convert.py` | plist → CSV，含恆等式驗證 |
| `tools/make_preview.js` | 產生本機預覽 `preview/index.html` |
| `data/*.csv` | 匯入 Google Sheet 用的資料 |
| `src/Ledger.gs` | 借貸引擎：各月餘額、月度/年度收支（伺服器端純函式） |
| `src/Code.gs` | Web App 進入點、`include()`、讀寫試算表、`importData`、通關密碼檢查、快取 |
| `src/index.html` | 前端骨架，以 `include()` 組入下列分層 |
| `src/View_Styles.html` | 樣式（CSS） |
| `src/Model.html` | 前端 Model：領域資料與純計算 |
| `src/Importer.html` | 前端 Model：解析 plist → 列陣列（與 `convert.py` 同結果） |
| `src/ViewModel.html` | 前端 ViewModel：畫面狀態、命令、可觀察通知 |
| `src/View.html` | 前端 View：DOM 綁定、Google Charts、事件轉發 |
| `src/appsscript.json` | GAS 專案設定 |
