/**
 * Code.gs — Web App 進入點與後端資料層
 *
 * 資料來源：與本腳本繫結(container-bound)的 Google 試算表中的兩個工作表
 *   - "Transactions" 欄位：Date, Month, Account1, Account2, Amount, Note1, Note2
 *   - "Accounts"     欄位：FullName, Type, TypeNote, ShortName, Active
 * （由 tools/convert.py 產生 CSV 後匯入，詳見 README.md）
 */

var TX_SHEET = 'Transactions';
var ACC_SHEET = 'Accounts';
var CACHE_KEY = 'timeseries_v1';
var CACHE_TTL = 21600; // 6 小時
var CODE_PROP = 'ACCESS_CODE'; // 通關密碼存於「指令碼屬性」，不寫進程式碼

/**
 * 設定通關密碼：在 Apps Script 編輯器把下面的 'change-me' 改成你的密碼，
 * 執行本函式一次即可（或改用：專案設定 → 指令碼屬性 → 新增屬性 ACCESS_CODE）。
 */
function setAccessCode() {
  PropertiesService.getScriptProperties().setProperty(CODE_PROP, 'change-me');
}

/** 驗證前端傳來的通關密碼；未設定或錯誤都擋下（錯誤時稍延遲以拖慢暴力猜測）。 */
function checkCode_(code) {
  var stored = PropertiesService.getScriptProperties().getProperty(CODE_PROP);
  if (!stored) throw new Error('尚未設定通關密碼，請先在 Apps Script 執行 setAccessCode 或於指令碼屬性設定 ACCESS_CODE');
  if (String(code || '') !== stored) { Utilities.sleep(800); throw new Error('密碼錯誤'); }
}

/** Web App 進入點（index 為模板，會以 include() 組入 Styles/Model/ViewModel/View） */
function doGet() {
  return HtmlService.createTemplateFromFile('index').evaluate()
    .setTitle('個人資產變化紀錄')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/** 供 index.html 以 <?!= include('檔名') ?> 組入其他 HTML 檔（MVVM 分層）。 */
function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

/** 讀取工作表為物件陣列（以第一列為欄位名）。 */
function readSheet(name) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name);
  if (!sh) throw new Error('找不到工作表：' + name + '（請依 README 匯入 CSV）');
  var values = sh.getDataRange().getValues();
  if (values.length < 2) return [];
  var header = values[0].map(function (h) { return String(h).trim(); });
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    var row = {};
    for (var j = 0; j < header.length; j++) row[header[j]] = values[i][j];
    rows.push(row);
  }
  return rows;
}

/** 由工作表建構交易物件陣列（欄位轉小寫、Month 正規化為 YYYY-MM 字串）。 */
function loadTransactions() {
  var raw = readSheet(TX_SHEET);
  return raw.map(function (r) {
    return {
      date: String(r.Date || ''),
      month: normalizeMonth(r.Month, r.Date),
      account1: String(r.Account1 || ''),
      account2: String(r.Account2 || ''),
      amount: Number(r.Amount) || 0,
      note1: String(r.Note1 || ''),
      note2: String(r.Note2 || '')
    };
  }).filter(function (t) { return t.account1 && t.account2 && t.month; });
}

/** Month 欄若被試算表轉成日期/數字，統一回 'YYYY-MM'。 */
function normalizeMonth(month, date) {
  if (month instanceof Date) return Utilities.formatDate(month, 'Asia/Taipei', 'yyyy-MM');
  var s = String(month || '').trim();
  if (/^\d{4}-\d{2}/.test(s)) return s.substring(0, 7);
  // 退而求其次：由 Date 欄推導
  if (date instanceof Date) return Utilities.formatDate(date, 'Asia/Taipei', 'yyyy-MM');
  var ds = String(date || '');
  if (/^\d{4}-\d{2}/.test(ds)) return ds.substring(0, 7);
  return s;
}

/** 前端主要資料來源：需通關密碼。 */
function getDashboardData(code) {
  checkCode_(code);
  return buildDashboardData_();
}

/** 實際組出儀表板資料（含快取）；內部使用，不做密碼檢查。 */
function buildDashboardData_() {
  var cache = CacheService.getUserCache();
  var cached = cache.get(CACHE_KEY);
  if (cached) return JSON.parse(cached);

  var txns = loadTransactions();
  var ts = buildTimeSeries(txns);

  // 帳戶顯示名稱 / 啟用狀態（可選，找不到 Accounts 表也不致命）
  var accMeta = {};
  try {
    readSheet(ACC_SHEET).forEach(function (a) {
      accMeta[String(a.FullName)] = {
        short: String(a.ShortName || a.FullName),
        typeNote: String(a.TypeNote || ''),
        active: String(a.Active) === '1' || a.Active === 1 || a.Active === true
      };
    });
  } catch (e) { /* 無 Accounts 表時忽略 */ }

  var result = {
    months: ts.months,
    totals: ts.totals,
    assetSeries: ts.assetSeries,
    liabilitySeries: ts.liabilitySeries,
    yearly: ts.yearly,
    accountMeta: accMeta,
    txnCount: txns.length,
    generatedAt: Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyy-MM-dd HH:mm')
  };

  try {
    cache.put(CACHE_KEY, JSON.stringify(result), CACHE_TTL);
  } catch (e) { /* 資料過大無法快取時略過 */ }
  return result;
}

/**
 * 前端上傳 source.plist 解析後呼叫：把資料寫入 Transactions / Accounts 工作表，
 * 清快取並回傳最新的儀表板資料。
 * @param {{transactions: Array<Array>, accounts: Array<Array>}} payload  皆含表頭列
 * @param {string} code  通關密碼
 */
function importData(payload, code) {
  checkCode_(code);
  if (!payload || !payload.transactions || !payload.transactions.length) {
    throw new Error('沒有可匯入的交易資料');
  }
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  writeSheet_(ss, TX_SHEET, payload.transactions);
  writeSheet_(ss, ACC_SHEET, payload.accounts || []);
  clearCache();
  return buildDashboardData_();
}

/** 以列陣列覆寫指定工作表（不存在則新建）；Month 欄設為純文字避免被轉成日期。 */
function writeSheet_(ss, name, rows) {
  var sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  sh.clearContents();
  if (!rows || !rows.length) return;
  var range = sh.getRange(1, 1, rows.length, rows[0].length);
  if (name === TX_SHEET) {
    sh.getRange(1, 1, rows.length, 2).setNumberFormat('@');   // Date、Month 兩欄以文字保存
  }
  range.setValues(rows);
}

/** 匯入或更新資料後，於試算表選單手動清除快取用。 */
function clearCache() {
  CacheService.getUserCache().remove(CACHE_KEY);
}

/** 開啟試算表時加入自訂選單，方便清快取與開啟網頁。 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('資產儀表板')
    .addItem('清除快取（更新資料後執行）', 'clearCache')
    .addToUi();
}
