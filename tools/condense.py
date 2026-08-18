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
    # 月更（推薦）：不帶任何參數即用智慧預設——來源 source.plist、經常性 6 科目、年份依當年自動判斷
    python3 tools/condense.py
    # 或用 Makefile 一鍵：make update（濃縮 → 轉 CSV → 開啟本機預覽）

    # 需要時仍可自訂：
    python3 tools/condense.py [科目名 ...] [--yearly-before N] [--monthly Y ...]
                              [--src 來源plist] [--out 輸出plist]
預設（皆可覆寫）：
    來源   = import_data/source.plist          （保持 raw；每月從 App 重新匯出覆蓋它）
    輸出   = import_data/source.condensed.plist
    科目   = 固定週期費、保險、日常生活、交通移動、健康醫療、進修教育
    年份   = 當年（不含）以前逐年、當年逐月——跨年自動生效，不用每年改參數
"""
import plistlib, os, sys, argparse, collections, datetime, re, shutil

TZ = datetime.timedelta(hours=8)   # plist 存 UTC(Z)；本人在 +8，年/月判斷需用當地時間
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 月更用途的預設：經常性、瑣碎的 6 類支出（旅遊／耐久大額／交通工具／房屋支出等單筆有意義者刻意不併）
DEFAULT_CATEGORIES = ["固定週期費", "保險", "日常生活", "交通移動", "健康醫療", "進修教育"]
# 年份邊界依「當年」自動判斷：往年（不含今年）逐年濃縮、今年逐月濃縮；跨年自動生效，不用每年改參數
THIS_YEAR = datetime.date.today().year

# 既有彙總筆的 Note1 形如「2026-08 日常生活彙總（46 筆）」；重複濃縮時把 N 讀出來累加，計數才不會退化成 1
_AGG_RE = re.compile(r"彙總（(\d+) 筆）")
def weight_of(t):
    m = _AGG_RE.search(t.get("Note1", "") or "")
    return int(m.group(1)) if m else 1


def parse_args():
    p = argparse.ArgumentParser(description="依 (往來科目 × 期間) 濃縮指定支出科目的交易")
    p.add_argument("categories", nargs="*", default=list(DEFAULT_CATEGORIES),
                   help="要濃縮的支出科目名（不含 E- 前綴），可多個；預設為經常性 6 科目：" + "、".join(DEFAULT_CATEGORIES))
    p.add_argument("--src", default=os.path.join(ROOT, "import_data", "source.plist"),
                   help="來源 plist；預設 import_data/source.plist")
    p.add_argument("--out", default=os.path.join(ROOT, "import_data", "source.condensed.plist"))
    p.add_argument("--in-place", action="store_true",
                   help="就地濃縮：先備份 --src 為 .bak，恆等式通過後把結果寫回 --src（月更工作流 A）")
    p.add_argument("--yearly-before", type=int, default=THIS_YEAR,
                   help="此年（不含）以前 → 每年濃縮一筆；預設『當年』（往年逐年）")
    p.add_argument("--monthly", type=int, nargs="*", default=None,
                   help="這些年份 → 每月濃縮一筆；預設『當年』。給 --monthly 但不接年份＝不做逐月")
    a = p.parse_args()
    if not a.categories:
        a.categories = list(DEFAULT_CATEGORIES)
    if a.monthly is None:            # 未指定 → 當年逐月（跨年自動生效）
        a.monthly = [THIS_YEAR]
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
    """回傳 (期間標籤, 該期間第一天的當地正午)；不需濃縮則回傳 None。
    彙總筆一律落在期間第一天（月→當月 1 號、年→該年 1/1）；用正午以免 ±8 時區換算跨到前一天。"""
    y, mo = local_dt.year, local_dt.month
    if y < yearly_before:
        return f"{y}", datetime.datetime(y, 1, 1, 12, 0, 0)
    if y in monthly_years:
        return f"{y}-{mo:02d}", datetime.datetime(y, mo, 1, 12, 0, 0)
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
        g = groups.setdefault(key, {"amount": 0.0, "count": 0, "date": rep_local - TZ})   # 當地正午 −8h 存回 UTC
        g["amount"] += float(t.get("Amount", 0) or 0)
        g["count"] += weight_of(t)   # 累加：既有彙總筆的 N 讀出來加總，重複濃縮計數不退化

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

    # ── 寫檔前先驗會計恆等式（濃縮前後 A-L 與 I-E 兩邊都須一致）；不過就中止、不寫任何檔 ──
    nw_after = net_worth(new_txns)
    diff_al, diff_ie = nw_after[0] - nw_before[0], nw_after[1] - nw_before[1]
    if abs(diff_al) >= 1 or abs(diff_ie) >= 1:
        print("❌ 會計恆等式不一致，已中止（未寫任何檔）：")
        print(f"   淨值 A-L 差額 = {diff_al:,.2f}　收支 I-E 差額 = {diff_ie:,.2f}")
        sys.exit(1)

    # in-place：先備份 --src 為 .bak，再把結果寫回 --src；否則寫到 --out
    out_path = args.src if args.in_place else args.out
    bak_path = None
    if args.in_place:
        bak_path = args.src + ".bak"
        shutil.copy2(args.src, bak_path)
    with open(out_path, "wb") as f:
        plistlib.dump(data, f)

    # ── 摘要與驗證 ──
    print(f"來源：{args.src}")
    if bak_path:
        print(f"備份：{bak_path}")
    print(f"輸出：{out_path}" + ("　（就地覆蓋）" if args.in_place else ""))
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

    print("\n---- 會計恆等式驗證（濃縮前後應一致；已於寫檔前把關）----")
    print(f"淨值 A-L　濃縮前 = {nw_before[0]:,.0f}　濃縮後 = {nw_after[0]:,.0f}　差額 = {diff_al:,.2f}")
    print(f"收支 I-E　濃縮前 = {nw_before[1]:,.0f}　濃縮後 = {nw_after[1]:,.0f}　差額 = {diff_ie:,.2f}")
    print("✅ 通過" if abs(diff_al) < 1 and abs(diff_ie) < 1 else "❌ 不一致")


if __name__ == "__main__":
    main()
