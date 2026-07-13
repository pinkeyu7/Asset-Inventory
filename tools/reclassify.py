#!/usr/bin/env python3
"""
一次性重整支出科目：將記帳 App 匯出的 source.plist 內 26 個支出(E)科目
合併為 14 個，輸出一份「維持 plist 格式」的新檔，原始檔不動。

同時處理兩處：
  1. Accounts     — 把舊支出科目換成合併後的新科目（初始金額加總、有任一啟用即啟用）
  2. MainData     — 把每筆交易 Account1/Account2 內對舊支出科目的參照改指到新科目

其餘（資產/負債/收入科目、DateScope、金額格式、Note）原樣保留。

用法：
    python3 tools/reclassify.py [來源plist] [輸出plist]
預設：
    來源 = import_data/source.plist
    輸出 = import_data/source.reclassified.plist
"""
import plistlib, os, sys, collections

# ───────────────────────────────────────────────────────────────────
# 支出科目重分類表：舊科目名 → 新科目名（可自由修改）
# 交易與科目都用「類型前綴 + 名稱」表示，例如 E-餐費；此處只列名稱部分。
# ───────────────────────────────────────────────────────────────────
REMAP = {
    # 01 固定週期費
    "水電瓦斯費": "固定週期費", "電信費": "固定週期費",
    "網路第四台": "固定週期費", "軟體訂閱費用": "固定週期費",
    # 02 保險
    "保險費用": "保險",
    # 03 日常生活
    "餐費": "日常生活", "飲料": "日常生活", "生活消耗品": "日常生活",
    "生活常態服務": "日常生活", "交際贈送費用": "日常生活",
    # 04 耐久大額
    "電子產品費用": "耐久大額", "家電產品費用": "耐久大額", "生活硬體": "耐久大額",
    # 05 交通工具
    "交通工具購買維修": "交通工具",
    # 06 交通移動
    "交通": "交通移動",
    # 07 健康醫療
    "醫療": "健康醫療",
    # 08 進修教育
    "補教用品費用": "進修教育",
    # 09 家人專款（原「人際家庭」，現只剩 Mom專款）
    "Mom專款": "家人專款",
    # 10 旅遊
    "旅遊": "旅遊",
    # 11 稅費雜支
    "稅費雜支": "稅費雜支",
    # 12~14 房產（規費設備＋雜支 各併成一條）
    "龜山-房屋規費設備": "龜山-房屋支出", "龜山-房屋雜支": "龜山-房屋支出",
    "新莊-房屋規費設備": "新莊-房屋支出", "新莊-房屋雜支": "新莊-房屋支出",
    "土城-房屋規費設備": "土城-房屋支出", "土城-房屋雜支": "土城-房屋支出",
}

# 新支出科目在 Accounts 內的呈現順序
NEW_ORDER = [
    "固定週期費", "保險", "日常生活", "耐久大額", "交通工具", "交通移動",
    "健康醫療", "進修教育", "家人專款", "旅遊", "稅費雜支",
    "龜山-房屋支出", "新莊-房屋支出", "土城-房屋支出",
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "import_data", "source.plist")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "import_data", "source.reclassified.plist")


def acct_name(full):
    """交易/科目字串為「類型前綴 + 名稱」，去掉開頭 'X-' 取名稱；名稱本身可含 '-'。"""
    return full[2:] if len(full) > 2 and full[1] == "-" else full


def main():
    with open(SRC, "rb") as f:
        data = plistlib.load(f)

    accounts = data.get("Accounts", [])
    txns = data.get("MainData", [])

    # 完整性檢查：所有出現過的支出科目都必須在 REMAP 內
    seen = set()
    for a in accounts:
        if (a.get("Type", "") or "").startswith("E"):
            seen.add(a.get("Name", ""))
    for t in txns:
        for k in ("Account1", "Account2"):
            v = t.get(k, "")
            if v.startswith("E-"):
                seen.add(acct_name(v))
    unmapped = seen - set(REMAP)
    if unmapped:
        sys.exit(f"❌ 有支出科目未列入 REMAP，請補上後再執行：{sorted(unmapped)}")

    # ── 1. 重建 Accounts：非支出科目原樣保留；支出科目合併成 NEW_ORDER ──
    merged = collections.OrderedDict((n, {"Amount": 0.0, "State": False}) for n in NEW_ORDER)
    non_expense = []
    for a in accounts:
        if (a.get("Type", "") or "").startswith("E"):
            new_name = REMAP[a.get("Name", "")]
            merged[new_name]["Amount"] += float(a.get("Amount", 0) or 0)
            merged[new_name]["State"] = merged[new_name]["State"] or bool(a.get("State"))
        else:
            non_expense.append(a)

    new_expense_accounts = []
    for n in NEW_ORDER:
        amt = merged[n]["Amount"]
        new_expense_accounts.append({
            "Amount": (int(amt) if float(amt).is_integer() else amt),
            "Name": n,
            "State": merged[n]["State"],
            "Type": "E-",
            "TypeNote": "支出(E)",
        })
    data["Accounts"] = non_expense + new_expense_accounts

    # ── 2. 重寫 MainData 的科目參照 ──
    remapped = 0
    for t in txns:
        for k in ("Account1", "Account2"):
            v = t.get(k, "")
            if v.startswith("E-"):
                new_full = "E-" + REMAP[acct_name(v)]
                if new_full != v:
                    t[k] = new_full
                    remapped += 1

    with open(OUT, "wb") as f:
        plistlib.dump(data, f)

    # ── 3. 驗證與摘要 ──
    print(f"來源：{SRC}")
    print(f"輸出：{OUT}")
    print(f"支出科目：{len(seen)} → {len(NEW_ORDER)}　交易科目參照改寫：{remapped} 處\n")

    cnt = collections.defaultdict(int)
    amt = collections.defaultdict(float)
    for t in txns:
        for k in ("Account1", "Account2"):
            v = t.get(k, "")
            if v.startswith("E-"):
                cnt[acct_name(v)] += 1
                amt[acct_name(v)] += float(t.get("Amount", 0) or 0)
    print(f"{'新支出科目':<14}{'筆數':>6}   金額(累計)")
    print("-" * 44)
    for n in NEW_ORDER:
        print(f"{n:<12}{cnt[n]:>7}   {amt[n]:>14,.0f}")

    # 會計恆等式：只改名不動金額，結果應與原檔完全一致
    _verify_identity(txns)


def _verify_identity(txns):
    DEBIT_NORMAL = {"A", "E"}
    deb = collections.defaultdict(float)
    cred = collections.defaultdict(float)
    for t in txns:
        a1, a2, m = t.get("Account1", ""), t.get("Account2", ""), float(t.get("Amount", 0) or 0)
        if a1[:1] == "I":            # 收入例外：借貸互換
            d_acc, c_acc = a2, a1
        else:
            d_acc, c_acc = a1, a2
        deb[d_acc] += m
        cred[c_acc] += m

    def natural(a):
        return (deb[a] - cred[a]) if a[:1] in DEBIT_NORMAL else (cred[a] - deb[a])

    allacc = set(deb) | set(cred)
    TA = sum(natural(a) for a in allacc if a[:1] == "A")
    TL = sum(natural(a) for a in allacc if a[:1] == "L")
    TI = sum(natural(a) for a in allacc if a[:1] == "I")
    TE = sum(natural(a) for a in allacc if a[:1] == "E")
    diff = (TA - TL) - (TI - TE)
    print("\n---- 會計恆等式驗證（重分類不應改變）----")
    print(f"淨值 A-L = {TA - TL:,.0f}　收入-支出 I-E = {TI - TE:,.0f}")
    print(f"差額（應為 0）= {diff:,.2f}   {'✅ 通過' if abs(diff) < 1 else '❌ 不一致'}")


if __name__ == "__main__":
    main()
