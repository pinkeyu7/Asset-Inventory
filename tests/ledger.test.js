/**
 * Ledger.gs 單元測試（Node 原生 node:test，無外部相依）。
 *   執行： node --test        （或： node --test tests/）
 *
 * Ledger.gs 是純 JS，直接以 eval 載入到本檔作用域（與 tools/make_preview.js 相同手法），
 * 之後就能呼叫其中的全域函式。重點鎖住「反推的借貸規則」與會計恆等式這條正確性防線。
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.dirname(__dirname);
eval(fs.readFileSync(path.join(ROOT, 'src', 'Ledger.gs'), 'utf8'));

test('typeOf：取全名第一字元', () => {
  assert.equal(typeOf('A-台新-Richart'), 'A');
  assert.equal(typeOf('I-薪資'), 'I');
  assert.equal(typeOf(''), '?');
});

test('debitCredit：一般為 A1 借方 / A2 貸方', () => {
  assert.deepEqual(debitCredit({ account1: 'E-伙食', account2: 'A-現金' }),
    { debit: 'E-伙食', credit: 'A-現金' });
});

test('debitCredit：A1 為收入(I) 時借貸互換', () => {
  assert.deepEqual(debitCredit({ account1: 'I-薪資', account2: 'A-現金' }),
    { debit: 'A-現金', credit: 'I-薪資' });
});

test('contribution：借方正常(A/E) 借增貸減；貸方正常(L/I) 反之', () => {
  assert.equal(contribution('A-現金', true, 100), 100);   // 資產在借方 → +
  assert.equal(contribution('A-現金', false, 100), -100);  // 資產在貸方 → −
  assert.equal(contribution('L-信用卡', false, 100), 100); // 負債在貸方 → +
  assert.equal(contribution('I-薪資', false, 100), 100);   // 收入在貸方 → +
  assert.equal(contribution('E-伙食', true, 100), 100);    // 支出在借方 → +
});

test('monthIndex / indexToMonth 為互逆', () => {
  for (const ym of ['2013-01', '2020-12', '2026-07']) {
    assert.equal(indexToMonth(monthIndex(ym)), ym);
  }
  assert.equal(monthIndex('2024-02') - monthIndex('2024-01'), 1);
  assert.equal(monthIndex('2025-01') - monthIndex('2024-12'), 1); // 跨年連續
});

// 手算情境：薪資入帳 → 現金花用 → 刷卡（負債）消費
const SCENARIO = [
  { month: '2024-01', account1: 'I-薪資', account2: 'A-現金', amount: 1000 }, // 收入 +1000，現金 +1000
  { month: '2024-01', account1: 'E-伙食', account2: 'A-現金', amount: 300 },  // 支出 +300，現金 −300
  { month: '2024-02', account1: 'E-購物', account2: 'L-信用卡', amount: 200 }, // 支出 +200，負債 +200
];

test('buildTimeSeries：逐月累積淨值與年度/月度收支', () => {
  const ts = buildTimeSeries(SCENARIO);
  assert.deepEqual(ts.months, ['2024-01', '2024-02']);

  // 1 月底：現金 700、無負債、淨值 700
  assert.deepEqual(ts.totals[0], { assets: 700, liabilities: 0, networth: 700 });
  // 2 月底：現金 700、負債 200、淨值 500
  assert.deepEqual(ts.totals[1], { assets: 700, liabilities: 200, networth: 500 });

  // 年度：收入 1000、支出 500、淨 500
  assert.deepEqual(ts.yearly, [{ year: '2024', income: 1000, expense: 500, net: 500 }]);
  // 月度與 months 對齊
  assert.deepEqual(ts.monthly[0], { income: 1000, expense: 300, net: 700 });
  assert.deepEqual(ts.monthly[1], { income: 0, expense: 200, net: -200 });

  // 各年收入/支出帳戶明細
  assert.equal(ts.incomeByYear['2024']['I-薪資'], 1000);
  assert.equal(ts.expenseByYear['2024']['E-伙食'], 300);
  assert.equal(ts.expenseByYear['2024']['E-購物'], 200);
});

test('verifyIdentity：正常複式資料恆等式成立（差額 0）', () => {
  const r = verifyIdentity(SCENARIO);
  assert.equal(r.ok, true);
  assert.equal(r.diff, 0);
  assert.equal(r.assets - r.liabilities, r.income - r.expense);
});

test('verifyIdentity：帳戶前綴非 A/L/I/E（解析錯位）會被抓出來', () => {
  // 現金增加但對手帳戶型別無法辨識 → 被排除在四類加總外，差額 ≠ 0
  const bad = [{ month: '2024-01', account1: 'A-現金', account2: 'X-亂碼', amount: 100 }];
  const r = verifyIdentity(bad);
  assert.equal(r.ok, false);
  assert.notEqual(r.diff, 0);
});

// 若已產生真實資料（data/transactions.csv），一併驗證恆等式（無檔則略過）
test('verifyIdentity：真實資料恆等式成立', (t) => {
  const csv = path.join(ROOT, 'data', 'transactions.csv');
  if (!fs.existsSync(csv)) return t.skip('尚未產生 data/transactions.csv');
  const lines = fs.readFileSync(csv, 'utf8').replace(/\r/g, '').trim().split('\n').slice(1);
  const txns = lines.map((line) => {
    const c = line.split(',');
    return { account1: c[2], account2: c[3], amount: parseFloat(c[4]) || 0 };
  }).filter((t) => t.account1 && t.account2);
  const r = verifyIdentity(txns);
  assert.equal(r.ok, true, `真實資料恆等式差額應為 0，實得 ${r.diff}`);
});
