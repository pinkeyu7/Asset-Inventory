#!/usr/bin/env python3
"""
將記帳 App 匯出的 XML plist 轉成兩個可匯入 Google Sheet 的 CSV：
  - data/accounts.csv      帳戶清單（名稱 / 類型 / 是否啟用）
  - data/transactions.csv  交易明細（原始 A1/A2/金額，借貸規則交由 GAS 端 Ledger.gs 計算）

用法：
    python3 tools/convert.py [來源plist路徑] [輸出資料夾]
預設：
    來源 = import_data/source.plist
    輸出 = data/

借貸規則（與 src/Ledger.gs 相同，僅在此做驗證，不寫進 CSV）：
    A1 = 借方(debit)、A2 = 貸方(credit)；當 A1 為收入(I) 時借貸互換。
    正確性檢查：總資產 − 總負債 應等於 累積收入 − 累積支出。
"""
import plistlib, csv, os, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "import_data", "source.plist")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "data")
os.makedirs(OUT, exist_ok=True)

with open(SRC, "rb") as f:
    data = plistlib.load(f)

accounts = data.get("Accounts", [])
txns = data.get("MainData", [])

def acct_type(full_name):
    """交易裡的帳戶字串為 「類型前綴 + 名稱」，類型取第一個字元：A/L/I/E。"""
    return full_name[0] if full_name else "?"

# ---------- accounts.csv ----------
acc_path = os.path.join(OUT, "accounts.csv")
with open(acc_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["FullName", "Type", "TypeNote", "ShortName", "Active"])
    for a in accounts:
        short = a.get("Name", "")
        typ = (a.get("Type", "") or "").rstrip("-")[:1]  # 'A-' -> 'A'
        full = f"{typ}-{short}"
        w.writerow([full, typ, a.get("TypeNote", ""), short, "1" if a.get("State") else "0"])

# ---------- transactions.csv ----------
tx_path = os.path.join(OUT, "transactions.csv")
rows = []
for t in txns:
    d = t.get("Date")
    iso = d.strftime("%Y-%m-%dT%H:%M:%S") if d else ""
    month = d.strftime("%Y-%m") if d else ""
    rows.append([
        iso, month,
        t.get("Account1", ""), t.get("Account2", ""),
        float(t.get("Amount", 0)),
        t.get("Note1", ""), t.get("Note2", ""),
    ])
rows.sort(key=lambda r: r[0])  # 依日期排序
with open(tx_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Date", "Month", "Account1", "Account2", "Amount", "Note1", "Note2"])
    w.writerows(rows)

# ---------- 驗證：會計恆等式 ----------
DEBIT_NORMAL = {"A", "E"}
deb = collections.defaultdict(float)
cred = collections.defaultdict(float)
for t in txns:
    a1, a2, m = t.get("Account1", ""), t.get("Account2", ""), float(t.get("Amount", 0))
    if acct_type(a1) == "I":      # 收入例外：借貸互換
        d_acc, c_acc = a2, a1
    else:
        d_acc, c_acc = a1, a2
    deb[d_acc] += m
    cred[c_acc] += m

def natural(a):
    return (deb[a] - cred[a]) if acct_type(a) in DEBIT_NORMAL else (cred[a] - deb[a])

allacc = set(deb) | set(cred)
TA = sum(natural(a) for a in allacc if acct_type(a) == "A")
TL = sum(natural(a) for a in allacc if acct_type(a) == "L")
TI = sum(natural(a) for a in allacc if acct_type(a) == "I")
TE = sum(natural(a) for a in allacc if acct_type(a) == "E")

print(f"帳戶數：{len(accounts)}　交易數：{len(txns)}")
print(f"輸出：{acc_path}")
print(f"輸出：{tx_path}")
print("---- 會計恆等式驗證 ----")
print(f"總資產 A            = {TA:,.0f}")
print(f"總負債 L            = {TL:,.0f}")
print(f"淨值 A-L            = {TA - TL:,.0f}")
print(f"累積收入-支出 I-E   = {TI - TE:,.0f}")
diff = (TA - TL) - (TI - TE)
print(f"差額（應為 0）      = {diff:,.2f}   {'✅ 通過' if abs(diff) < 1 else '❌ 不一致'}")
