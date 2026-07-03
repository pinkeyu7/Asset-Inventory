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

/** 前端主要資料來源：回傳完整時間序列 + 帳戶顯示資訊（含快取）。 */
function getDashboardData() {
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
