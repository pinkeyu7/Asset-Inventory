/**
 * 產生本機預覽：用真實資料算出 dashboard payload，注入 src/index.html，
 * 輸出 preview/index.html（可直接用瀏覽器開啟，無需部署 GAS）。
 *
 * 用法： node tools/make_preview.js
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.dirname(__dirname);

// 1) 載入 Ledger.gs（純 JS）
eval(fs.readFileSync(path.join(ROOT, 'src', 'Ledger.gs'), 'utf8'));

// 2) 讀 CSV（處理 note 內含逗號：僅切前 7 欄）
function readCsv(file) {
  const lines = fs.readFileSync(file, 'utf8').replace(/\r/g, '').trim().split('\n');
  const header = lines[0].split(',');
  return lines.slice(1).map(line => {
    const cells = line.split(',');
    const obj = {};
    header.forEach((h, i) => { obj[h] = cells[i]; });
    return obj;
  });
}

const txRows = readCsv(path.join(ROOT, 'data', 'transactions.csv'));
const txns = txRows.map(r => ({
  date: r.Date, month: r.Month, account1: r.Account1, account2: r.Account2,
  amount: parseFloat(r.Amount) || 0, note1: r.Note1 || '', note2: r.Note2 || ''
})).filter(t => t.account1 && t.account2 && t.month);

const ts = buildTimeSeries(txns);

const accMeta = {};
try {
  readCsv(path.join(ROOT, 'data', 'accounts.csv')).forEach(a => {
    accMeta[a.FullName] = { short: a.ShortName || a.FullName, typeNote: a.TypeNote || '', active: a.Active === '1' };
  });
} catch (e) {}

const payload = {
  months: ts.months, totals: ts.totals, assetSeries: ts.assetSeries,
  liabilitySeries: ts.liabilitySeries, yearly: ts.yearly, accountMeta: accMeta,
  txnCount: txns.length, generatedAt: '(本機預覽)'
};

// 3) 注入 index.html：把 google.script.run 區塊換成內嵌資料
let html = fs.readFileSync(path.join(ROOT, 'src', 'index.html'), 'utf8');
const runBlock = /google\.script\.run[\s\S]*?\.getDashboardData\(\);/;
if (!runBlock.test(html)) { console.error('找不到 google.script.run 區塊，無法注入'); process.exit(1); }
html = html.replace(runBlock, 'DATA = ' + JSON.stringify(payload) + '; maybeRender();');

const outDir = path.join(ROOT, 'preview');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'index.html'), html);

const last = ts.totals[ts.totals.length - 1];
console.log('已產生 preview/index.html');
console.log('  交易', txns.length, '筆 ·', ts.months.length, '個月 ·', ts.months[0], '→', ts.months[ts.months.length - 1]);
console.log('  最新淨值', Math.round(last.networth).toLocaleString(), '元');
console.log('  用瀏覽器開啟： open preview/index.html');
