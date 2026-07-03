# 個人資產變化紀錄

把記帳 App 匯出的複式記帳資料，變成一個可視化的個人淨值儀表板 —— 顯示**淨值趨勢、資產組成佔比、年度收支總結**。以 Google Apps Script（Google Sheet 當資料庫、`HtmlService` 出網頁）打造，零伺服器成本。

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
Web App（src/index.html，Google Charts）＝ 儀表板
```

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

1. **建立試算表**：新建一個 Google Sheet。
2. **匯入資料**：在該 Sheet 中
   - 建立工作表 `Transactions`，`檔案 → 匯入 → 上傳 data/transactions.csv`，匯入位置選「取代目前工作表」。
   - 建立工作表 `Accounts`，同樣匯入 `data/accounts.csv`。
3. **建立繫結腳本**：在 Sheet 選 `擴充功能 → Apps Script`，會開啟一個繫結此試算表的專案。
4. **取得 scriptId**：Apps Script 專案 `專案設定 → 指令碼 ID`，複製它。
5. **設定 clasp**：
   ```bash
   clasp login
   cp .clasp.json.example .clasp.json     # 把 scriptId 填進去
   clasp push                              # 上傳 src/ 內的檔案
   ```
6. **部署為 Web App**：Apps Script → `部署 → 新增部署 → 類型選「網頁應用程式」`，
   執行身分＝自己、存取權＝僅限自己，部署後即得專屬網址。

### 4. 更新資料

覆蓋 `source.plist` → 跑 `convert.py` → 重新匯入兩個工作表 → 在試算表選單
`資產儀表板 → 清除快取`（或等 6 小時快取自動過期）→ 重新整理網頁。

## 檔案

| 路徑 | 說明 |
|------|------|
| `import_data/source.plist` | 記帳 App 匯出的原始檔（不會被修改） |
| `tools/convert.py` | plist → CSV，含恆等式驗證 |
| `tools/make_preview.js` | 產生本機預覽 `preview/index.html` |
| `data/*.csv` | 匯入 Google Sheet 用的資料 |
| `src/Ledger.gs` | 借貸與各月餘額計算引擎（純函式） |
| `src/Code.gs` | Web App 進入點、讀取試算表、快取 |
| `src/index.html` | 前端儀表板（三個畫面 + Google Charts） |
| `src/appsscript.json` | GAS 專案設定 |
