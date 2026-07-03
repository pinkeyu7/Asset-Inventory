/**
 * Ledger.gs — 複式記帳借貸引擎（純函式，可單元測試）
 *
 * 借貸規則（由來源資料反推、以會計恆等式驗證）：
 *   每筆交易 A1 = 借方(debit)、A2 = 貸方(credit)；
 *   唯一例外：當 A1 的類型為收入(I) 時，借貸互換（A2 為借方、A1 為貸方）。
 *
 * 帳戶類型（取全名第一個字元）：
 *   A 資產、L 負債、I 收入、E 支出。
 *   借方正常餘額(debit-normal)：A、E  → 借增貸減
 *   貸方正常餘額(credit-normal)：L、I → 貸增借減
 *
 * 會計恆等式（正確性保證）：Σ資產 − Σ負債 === Σ收入 − Σ支出
 */

var DEBIT_NORMAL = { A: true, E: true };

/** 取帳戶類型字元，例：'A-台新銀行-Richart' -> 'A' */
function typeOf(fullName) {
  return fullName ? String(fullName).charAt(0) : '?';
}

/** 判斷某交易中，account 位於借方或貸方後，對該帳戶「正常餘額」的變化量（含正負號）。 */
function contribution(fullName, isDebitSide, amount) {
  var debitNormal = !!DEBIT_NORMAL[typeOf(fullName)];
  // 位於借方且借方正常 → +；位於貸方且貸方正常 → +；其餘 → −
  var positive = (isDebitSide === debitNormal);
  return positive ? amount : -amount;
}

/** 回傳 {debit, credit}：該交易的借方、貸方帳戶全名。 */
function debitCredit(t) {
  if (typeOf(t.account1) === 'I') {
    return { debit: t.account2, credit: t.account1 };
  }
  return { debit: t.account1, credit: t.account2 };
}

/** 'YYYY-MM' -> 連續月份索引（可比較、可相減）。 */
function monthIndex(ym) {
  var p = String(ym).split('-');
  return parseInt(p[0], 10) * 12 + (parseInt(p[1], 10) - 1);
}

/** 連續月份索引 -> 'YYYY-MM' */
function indexToMonth(idx) {
  var y = Math.floor(idx / 12);
  var m = (idx % 12) + 1;
  return y + '-' + (m < 10 ? '0' + m : '' + m);
}

/**
 * 由交易明細計算完整時間序列。
 * @param {Array<{date,month,account1,account2,amount,note1,note2}>} txns
 * @param {Object<string,string>} typeNoteByType  例如 {A:'資產(A)', ...}（可選，僅供顯示）
 * @return {Object} { months, totals, assetSeries, liabilitySeries, yearly, accountBalances }
 */
function buildTimeSeries(txns) {
  if (!txns.length) {
    return { months: [], totals: [], assetSeries: {}, liabilitySeries: {}, yearly: [], accountBalances: {} };
  }

  // 1) 每月、每帳戶的變化量彙總
  var deltaByMonthAccount = {};   // { monthIdx: { account: delta } }
  var accountsSeen = {};          // account -> type
  var minIdx = Infinity, maxIdx = -Infinity;

  for (var i = 0; i < txns.length; i++) {
    var t = txns[i];
    var idx = monthIndex(t.month);
    if (idx < minIdx) minIdx = idx;
    if (idx > maxIdx) maxIdx = idx;
    var dc = debitCredit(t);
    var amt = Number(t.amount) || 0;

    accountsSeen[t.account1] = typeOf(t.account1);
    accountsSeen[t.account2] = typeOf(t.account2);

    if (!deltaByMonthAccount[idx]) deltaByMonthAccount[idx] = {};
    var bucket = deltaByMonthAccount[idx];
    bucket[dc.debit]  = (bucket[dc.debit]  || 0) + contribution(dc.debit,  true,  amt);
    bucket[dc.credit] = (bucket[dc.credit] || 0) + contribution(dc.credit, false, amt);
  }

  // 2) 連續月份清單（補齊中間沒有交易的月份，讓折線連續）
  var months = [];
  for (var m = minIdx; m <= maxIdx; m++) months.push(indexToMonth(m));

  // 3) 逐月累加，產生各序列
  var running = {};                 // account -> 累積餘額
  Object.keys(accountsSeen).forEach(function (a) { running[a] = 0; });

  var assetAccts = Object.keys(accountsSeen).filter(function (a) { return accountsSeen[a] === 'A'; });
  var liabAccts  = Object.keys(accountsSeen).filter(function (a) { return accountsSeen[a] === 'L'; });

  var totals = [];
  var assetSeries = {}; assetAccts.forEach(function (a) { assetSeries[a] = []; });
  var liabilitySeries = {}; liabAccts.forEach(function (a) { liabilitySeries[a] = []; });

  for (var j = 0; j < months.length; j++) {
    var idx2 = monthIndex(months[j]);
    var d = deltaByMonthAccount[idx2];
    if (d) {
      Object.keys(d).forEach(function (a) { running[a] = (running[a] || 0) + d[a]; });
    }
    var sumA = 0, sumL = 0;
    assetAccts.forEach(function (a) { sumA += running[a]; assetSeries[a].push(round2(running[a])); });
    liabAccts.forEach(function (a)  { sumL += running[a]; liabilitySeries[a].push(round2(running[a])); });
    totals.push({ assets: round2(sumA), liabilities: round2(sumL), networth: round2(sumA - sumL) });
  }

  // 4) 年度 / 月度收支，以及各年「各收入/支出帳戶」明細
  var yearlyMap = {};    // year     -> {income, expense}
  var monthlyMap = {};   // 'YYYY-MM'-> {income, expense}
  var incomeByYear = {}; // year     -> { 帳戶全名: 金額 }
  var expenseByYear = {};// year     -> { 帳戶全名: 金額 }
  for (var k = 0; k < txns.length; k++) {
    var tx = txns[k];
    var mo = String(tx.month);
    var year = mo.split('-')[0];
    if (!yearlyMap[year]) yearlyMap[year] = { income: 0, expense: 0 };
    if (!monthlyMap[mo]) monthlyMap[mo] = { income: 0, expense: 0 };
    var dc2 = debitCredit(tx);
    var a2 = Number(tx.amount) || 0;
    // 收入帳戶（貸方正常）：出現在貸方即為收入實現
    if (typeOf(dc2.credit) === 'I') {
      yearlyMap[year].income += a2; monthlyMap[mo].income += a2;
      if (!incomeByYear[year]) incomeByYear[year] = {};
      incomeByYear[year][dc2.credit] = (incomeByYear[year][dc2.credit] || 0) + a2;
    }
    // 支出帳戶（借方正常）：出現在借方即為支出發生
    if (typeOf(dc2.debit) === 'E') {
      yearlyMap[year].expense += a2; monthlyMap[mo].expense += a2;
      if (!expenseByYear[year]) expenseByYear[year] = {};
      expenseByYear[year][dc2.debit] = (expenseByYear[year][dc2.debit] || 0) + a2;
    }
  }
  var yearly = Object.keys(yearlyMap).sort().map(function (y) {
    var o = yearlyMap[y];
    return { year: y, income: round2(o.income), expense: round2(o.expense), net: round2(o.income - o.expense) };
  });
  // 與 months 對齊（無交易的月份為 0）
  var monthly = months.map(function (m) {
    var o = monthlyMap[m] || { income: 0, expense: 0 };
    return { income: round2(o.income), expense: round2(o.expense), net: round2(o.income - o.expense) };
  });

  return {
    months: months,
    totals: totals,
    assetSeries: assetSeries,
    liabilitySeries: liabilitySeries,
    yearly: yearly,
    monthly: monthly,
    incomeByYear: incomeByYear,
    expenseByYear: expenseByYear,
    accountBalances: running
  };
}

function round2(x) { return Math.round(x * 100) / 100; }
