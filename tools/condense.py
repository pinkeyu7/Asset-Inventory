#!/usr/bin/env python3
"""
歷史交易濃縮：把「涉及指定支出科目」的交易，依 (Account1, Account2, 期間) 分組加總成一筆，
藉此精簡多年累積的瑣碎紀錄。支援兩種顆粒度：

  --yearly-before N   N 年（不含）以前的交易 → 每『年』濃縮一筆
  --monthly Y ...     指定年份的交易         → 每『月』濃縮一筆（可多個年份）

未落入上述任一範圍的交易（含指定的當年及未濃縮年份、非目標科目）一律原樣保留。
分組保留原本借貸方向與金額總和，故淨值與各帳戶最終餘額不變；
且因採「年/月」為期間，對應顆粒度的統計（年報 / 月趨勢）仍成立。

用法：
    python3 tools/condense.py [科目名 ...] [--yearly-before 2026] [--monthly 2026 ...]
                              [--src 來源plist] [--out 輸出plist]
範例：
    # 2026 前逐年濃縮，2026 逐月濃縮（本專案目前的最終狀態）
    python3 tools/condense.py 固定週期費 保險 日常生活 交通移動 健康醫療 進修教育 \\
        --yearly-before 2026 --monthly 2026
預設：
    來源 = import_data/source.reclassified.plist
    輸出 = import_data/source.condensed.plist
    科目 = 日常生活
"""
import plistlib, os, sys, argparse, calendar, collections, datetime

TZ = datetime.timedelta(hours=8)   # plist 存 UTC(Z)；本人在 +8，年/月判斷需用當地時間
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_args():
    p = argparse.ArgumentParser(description="依 (往來科目 × 期間) 濃縮指定支出科目的交易")
    p.add_argument("categories", nargs="*", default=["日常生活"],
                   help="要濃縮的支出科目名（不含 E- 前綴），可多個；預設『日常生活』")
    p.add_argument("--src", default=os.path.join(ROOT, "import_data", "source.reclassified.plist"))
    p.add_argument("--out", default=os.path.join(ROOT, "import_data", "source.condensed.plist"))
    p.add_argument("--yearly-before", type=int, default=2026,
                   help="此年（不含）以前 → 每年濃縮一筆；預設 2026")
    p.add_argument("--monthly", type=int, nargs="*", default=[],
                   help="這些年份 → 每月濃縮一筆；可多個")
    a = p.parse_args()
    if not a.categories:
        a.categories = ["日常生活"]
    return a


def net_worth(txns):
    """會計恆等式左右兩邊，用來確認濃縮前後結果一致。"""
    DEBIT_NORMAL = {"A", "E"}
    deb, cred = collections.defaultdict(float), collections.defaultdict(float)
    for t in txns:
        a1, a2, m = t["Account1"], t["Account2"], float(t.get("Amount", 0) or 0)
        d_acc, c_acc = (a2, a1) if a1[:1] == "I" else (a1, a2)   # 收入借貸互換
        deb[d_acc] += m
        cred[c_acc] += m
    nat = lambda a: (deb[a] - cred[a]) if a[:1] in DEBIT_NORMAL else (cred[a] - deb[a])
    accs = set(deb) | set(cred)
    T = {ty: sum(nat(a) for a in accs if a[:1] == ty) for ty in "ALIE"}
    return T["A"] - T["L"], T["I"] - T["E"]


def period_of(local_dt, yearly_before, monthly_years):
    """回傳 (期間標籤, 該期間結束日的當地正午)；不需濃縮則回傳 None。"""
    y, mo = local_dt.year, local_dt.month
    if y < yearly_before:
        return f"{y}", datetime.datetime(y, 12, 31, 12, 0, 0)
    if y in monthly_years:
        last = calendar.monthrange(y, mo)[1]
        return f"{y}-{mo:02d}", datetime.datetime(y, mo, last, 12, 0, 0)
    return None


def main():
    args = parse_args()
    targets = {f"E-{c}" for c in args.categories}
    monthly_years = set(args.monthly)

    with open(args.src, "rb") as f:
        data = plistlib.load(f)
    txns = data.get("MainData", [])
    nw_before = net_worth(txns)

    # 分成「要濃縮」與「原樣保留」；同時記下每筆的期間標籤與代表日期
    to_condense, kept = [], []
    for t in txns:
        involved = t["Account1"] in targets or t["Account2"] in targets
        per = period_of(t["Date"] + TZ, args.yearly_before, monthly_years) if involved else None
        if per:
            to_condense.append((t, per[0], per[1]))
        else:
            kept.append(t)

    # 依 (Account1, Account2, 期間標籤) 分組加總 —— 借貸方向天然被 pair 保留
    groups = collections.OrderedDict()
    for t, label, rep_local in to_condense:
        key = (t["Account1"], t["Account2"], label)
        g = groups.setdefault(key, {"amount": 0.0, "count": 0, "date": rep_local - TZ})
        g["amount"] += float(t.get("Amount", 0) or 0)
        g["count"] += 1

    condensed = []
    for (a1, a2, label), g in groups.items():
        cat = a1 if a1 in targets else a2
        condensed.append({
            "Account1": a1, "Account2": a2,
            "Amount": g["amount"],
            "Color": 0,
            "Date": g["date"],
            "Done": False,   # 與原始帳本慣例一致（全帳幾乎皆 false）；辨識彙總請看 Note1
            "Note1": f"{label} {cat[2:]}彙總（{g['count']} 筆）",
            "Note2": "",
        })

    new_txns = kept + condensed
    new_txns.sort(key=lambda t: t["Date"])   # 依時間排序，維持帳本可讀性
    data["MainData"] = new_txns

    with open(args.out, "wb") as f:
        plistlib.dump(data, f)

    # ── 摘要與驗證 ──
    nw_after = net_worth(new_txns)
    print(f"來源：{args.src}")
    print(f"輸出：{args.out}")
    print(f"濃縮科目：{', '.join(args.categories)}")
    print(f"顆粒度：{args.yearly_before} 前逐年"
          + (f"、逐月年份 {sorted(monthly_years)}" if monthly_years else "") + "\n")
    print(f"被濃縮交易：{len(to_condense)} 筆 → 濃縮後：{len(condensed)} 筆")
    print(f"總交易數：{len(txns)} → {len(new_txns)}\n")

    print("濃縮明細（依期間）：")
    per = collections.defaultdict(lambda: [0, 0.0])
    for (a1, a2, label), g in groups.items():
        per[label][0] += 1
        per[label][1] += g["amount"]
    print(f"  {'期間':<9}{'筆數':>6}{'金額':>14}")
    for label in sorted(per):
        c, a = per[label]
        print(f"  {label:<9}{c:>6}{a:>14,.0f}")

    print("\n---- 會計恆等式驗證（濃縮前後應一致）----")
    diff = nw_after[0] - nw_before[0]
    print(f"淨值 A-L　濃縮前 = {nw_before[0]:,.0f}　濃縮後 = {nw_after[0]:,.0f}")
    print(f"差額（應為 0）= {diff:,.2f}   {'✅ 通過' if abs(diff) < 1 else '❌ 不一致'}")


if __name__ == "__main__":
    main()
