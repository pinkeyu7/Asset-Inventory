#!/usr/bin/env python3
"""
〈五年財務展望〉報告（src/view/View_Fire_Report.html）的逐月推演模型：
依報告「關鍵假設」逐月推演現金、0050、房貸與房產，印出報告各章用到的數字。

用法：
    python3 tools/fire_model.py

收支、房貸、獎金等假設寫在下方常數；改了之後重跑，再依輸出手動更新報告。
單位一律為「萬元」。
"""
import math

# ── 收支（第一章）──
START_CASH = 103.0                                        # 2026/10 初自有現金（已扣家人寄放與借款）
SALARY, PARTTIME, LIVING = 13.0, 2.5, 7.0                 # 月薪、兼職、生活費＋零用金
RENT_A, RENT_B = 2.3, 2.5                                 # 兩間合計 4.8（第一章取整口徑）
BONUS = {1: 12, 2: 12, 4: 8, 6: 8, 7: 8, 9: 8, 10: 8}     # 64 萬/年
RESERVE, CASH_RATE = 80.0, 0.015                          # 緊急預備金、定存年息
CAR_PRICE, CAR_COST, CAR_YEARS = 70.0, 1.0, 10            # 買車（2027/1 付現、每 10 年換）、每月養車費
HOUSE_G = 0.0                                             # 房價年漲幅（基準：持平）

# ── A、B 房 ──
A0, B0 = 1000.0, 1250.0                                   # 2026/10 市值
B_START, B_PAY, B_PAYOFF_MONTHS = 870.0, 4.9, 223         # B 房貸：2026/10 餘額、月付、約 2045/4 還清
A_COST, A_BROKER, A_MISC, A_TAX = 740.0, 0.04, 5.0, 0.20  # A：取得成本、仲介費率、代書雜費、房地合一稅率
A_NET_SALE = A0 - A0 * A_BROKER - A_MISC - (A0 - A_COST - A0 * A_BROKER) * A_TAX

# ── C 房：交屋即賣（〈C 房交屋即賣＋貸款方案〉：2b 貸款、2027/3 賣出）──
C_PRICE, C_COST, C_DEDUCT = 2100.0, 1812.0, 10.0          # 成交價、取得成本、交屋雜費中列入取得成本的部分
C_BROKER, C_MISC, C_TAX = 50.0, 6.0, 0.45                 # 仲介費、代書雜費、房地合一稅率（持有 2 年內）
C_LOAN, C_RATE, C_N = 1268.0, 0.03, 360                   # 2b：2027/1 起月付
C_SALE = (2027, 3)                                        # 繳完當月月付後賣出
MARTIN_INT, MOM_INT = 2.0, 20.0                           # 家人借款利息：2026/11 付 Martin、2026/12 交屋後付 Mom
C_TAX_AMT = (C_PRICE - C_COST - C_DEDUCT - C_BROKER) * C_TAX


def pmt(principal, annual_rate, months):
    r = annual_rate / 12
    return principal * r / (1 - (1 + r) ** -months)


def b_rate():
    """由 B 房貸「月付 4.9 萬、約 223 個月還清」反推年利率。"""
    lo, hi = 0.01, 0.05
    for _ in range(60):
        mid = (lo + hi) / 2
        n = -math.log(1 - B_START * mid / 12 / B_PAY) / math.log(1 + mid / 12)
        lo, hi = (mid, hi) if n < B_PAYOFF_MONTHS else (lo, mid)
    return mid


B_RATE = b_rate()
C_PAY = pmt(C_LOAN, C_RATE, C_N)

# 三個方案都在 2027/3 賣 C；賣房的錢先還 B，剩下的存 0050；住自己的房子或家裡，不付房租
PLANS = {
    '1': dict(),                                            # 住家裡
    '2': dict(live_in_b=True, car=True),                    # 住 B，買車
    '3': dict(sell_a=True, live_in_b=True, car=True),       # 賣 A，住 B，買車
}


def run(plan, etf_ret=0.06, house_g=HOUSE_G, cut=0.0, end_year=2031, invest_cap=None):
    """逐月推演 2026/10 ～ end_year/12，回傳 {年: 年底狀態, 'b_paid_off': (年, 月) 或 None,
    'low_2027': 2027 年現金最低點 (萬, 月)，取賣 C 入帳前}。

    plan 鍵：sell_a（2027/1 賣 A）、live_in_b（2027 起自住 B，不再收 B 租金）、car（2027/1 起買車並付養車費）。
    共通事件：2026/11、12 付家人借款利息；2027/1～3 繳 C 月付，2027/3 賣 C。
    2027 起超過預備金的現金（含賣屋所得）先還 B，B 還清前不投入 0050。
    cut：2027 起每月減薪；invest_cap：2028 起每月投入上限（模擬起步期一直不加碼）。
    投入節奏：2027 上半年每月 2 萬、下半年 4 萬；2028 起超過預備金的現金全數投入，
    2027 年底累積的待投入現金分 24 個月攤入。
    """
    cash, etf, b_bal, c_bal = START_CASH, 0.0, B_START, 0.0
    has_a = True
    pool = pool_step = 0.0
    b_paid_off, low = None, None
    etf_m = (1 + etf_ret) ** (1 / 12) - 1
    out, y, m, n = {}, 2026, 10, 0
    while (y, m) <= (end_year, 12):
        etf *= 1 + etf_m
        cash += max(cash, 0) * CASH_RATE / 12

        if (y, m) == (2026, 11):
            cash -= MARTIN_INT
        if (y, m) == (2026, 12):
            cash -= MOM_INT
        if (y, m) == (2027, 1):
            c_bal = C_LOAN
            if plan.get('sell_a'):
                has_a = False
                cash += A_NET_SALE
        if plan.get('car') and m == 1 and y >= 2027 and (y - 2027) % CAR_YEARS == 0:
            cash -= CAR_PRICE

        after = y >= 2027
        rent = (RENT_A if has_a else 0) + (0 if after and plan.get('live_in_b') else RENT_B)
        car = CAR_COST if after and plan.get('car') else 0
        cash += SALARY - (cut if after else 0) + PARTTIME + rent + BONUS.get(m, 0) - LIVING - car
        if b_bal > 0:
            interest = b_bal * B_RATE / 12
            pay = min(B_PAY, b_bal + interest)
            cash -= pay
            b_bal -= pay - interest
        if c_bal > 0:
            cash -= C_PAY
            c_bal -= C_PAY - c_bal * C_RATE / 12
        if y == 2027 and (low is None or cash < low[0]):
            low = (cash, m)
        if (y, m) == C_SALE:
            cash += C_PRICE - c_bal - C_BROKER - C_MISC - C_TAX_AMT
            c_bal = 0.0

        if after and b_bal > 0 and cash > RESERVE:
            x = min(cash - RESERVE, b_bal)
            cash -= x
            b_bal -= x
        if b_bal <= 1e-9 and b_paid_off is None:
            b_paid_off = (y, m)

        if y == 2027:
            want = 0 if b_bal > 0 else (2 if m <= 6 else 4)
            x = max(0.0, min(want, cash - RESERVE))
            cash -= x
            etf += x
        elif y >= 2028:
            if (y, m) == (2028, 1):
                pool = max(0.0, cash - RESERVE)
                pool_step = pool / 24
            pool = max(0.0, pool - pool_step)
            x = max(0.0, cash - RESERVE - pool)
            if invest_cap is not None:
                x, pool = min(x, invest_cap), 0.0
            cash -= x
            etf += x

        if m == 12:
            g = (1 + house_g) ** ((n + 1) / 12)
            prop = ((A0 if has_a else 0) + B0) * g
            debt = b_bal + c_bal
            out[y] = dict(avail=cash + etf, etf=etf, cash=cash, debt=debt, prop=prop,
                          nw=cash + etf + prop - debt)
        n += 1
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    out['b_paid_off'], out['low_2027'] = b_paid_off, low
    return out


def ceil1(x):
    return math.ceil(x * 10 - 1e-9) / 10


def rents_of(p):
    """2027 起各間收租的租金。"""
    return ([] if p.get('sell_a') else [RENT_A]) + ([] if p.get('live_in_b') else [RENT_B])


def monthly(k):
    """第一章算法（收入無條件捨去、支出無條件進位），B 還清後的平準月每月結餘。"""
    p = PLANS[k]
    return SALARY + PARTTIME + sum(rents_of(p)) - LIVING - (CAR_COST if p.get('car') else 0)


def main():
    R = {k: run(p) for k, p in PLANS.items()}
    R0 = {k: run(p, etf_ret=0) for k, p in PLANS.items()}   # 0% 報酬下 0050 餘額＝累計投入
    c_bal3 = C_LOAN
    for _ in range(3):
        c_bal3 -= C_PAY - c_bal3 * C_RATE / 12
    c_net = C_PRICE - c_bal3 - C_BROKER - C_MISC - C_TAX_AMT
    print(f"B 房貸反推利率 {B_RATE*100:.2f}%　C 月付 {C_PAY:.4f} 萬、3 期後餘額 {c_bal3:.1f}、稅 {C_TAX_AMT:.1f}、"
          f"賣出淨額 {c_net:.1f}　賣 A 淨入袋 {A_NET_SALE:.0f} 萬")
    three = SALARY + PARTTIME + RENT_A + RENT_B - LIVING - B_PAY - ceil1(C_PAY)
    print(f"三房並存（2027/1～3）：房貸 {B_PAY + ceil1(C_PAY):.1f}｜結餘 {three:.1f}｜降薪 {three-5:.1f}")
    cash12 = run(PLANS['1'], end_year=2026)[2026]['cash']
    print(f"2026/12 底現金 {cash12:.0f}")

    print("\n每月結餘（B 還清後）")
    for k, p in PLANS.items():
        s = monthly(k)
        rents = rents_of(p)
        vac = '～'.join(sorted({f'{s-r:.1f}' for r in rents})) if rents else '—'
        runway = f"{R[k][2027]['avail']/(SALARY-s):.0f} 個月" if s < SALARY else "不會虧"
        print(f"  {k} 結餘 {s:.1f}｜降薪 {s-5:.1f}｜一間空租 {vac}"
              f"｜預備金 6 個月 {(LIVING+(CAR_COST if p.get('car') else 0))*6:.0f}"
              f"｜失業可撐 2027 {runway}｜B 還清 {R[k]['b_paid_off']}"
              f"｜2027 最低現金 {R[k]['low_2027'][0]:.0f}（{R[k]['low_2027'][1]} 月）")

    print("\n每年年底　可動用／負債／淨資產（0050 6%）")
    for k in PLANS:
        print(f"  {k} " + "　".join(f"{y} {R[k][y]['avail']:.0f}／{R[k][y]['debt']:.0f}／{R[k][y]['nw']:.0f}"
                                   for y in range(2027, 2032)))

    print("\n2031 年底")
    for k, p in PLANS.items():
        r = R[k][2031]
        rent = sum(rents_of(p))
        lo, hi = run(p, etf_ret=0)[2031]['nw'], run(p, etf_ret=.08)[2031]['nw']
        print(f"  {k} 0050 {r['etf']:.0f}｜淨資產 0%～8% {lo:.0f}～{hi:.0f}｜被動收入 4% {rent + r['etf']*.04/12:.1f}"
              f"｜房產占總資產 {r['prop']/(r['prop']+r['avail'])*100:.0f}%"
              f"｜現金與 0050 占 {r['avail']/(r['prop']+r['avail'])*100:.0f}%"
              f"｜0050 跌 30% 淨資產 {r['nw']-.3*r['etf']:.0f}（少 {.3*r['etf']:.0f}）")

    print("\n投入時程")
    for k in PLANS:
        r, r0 = R[k], R0[k]
        pend = r[2027]['cash'] - RESERVE
        contrib = [r0[y]['etf'] - (r0[y-1]['etf'] if y > 2027 else 0) for y in range(2027, 2032)]
        print(f"  {k} 2027 年底現金 {r[2027]['cash']:.0f}（待投入 {pend:.0f}，2028～29 每月攤 {pend/24:.1f}）"
              f"｜每年投入 " + "/".join(f"{c:.0f}" for c in contrib))

    print("\n55 歲（2046 年底）淨資產：0050 0/4/6/8%｜房價年漲 −1/+1/+2%（0050 6%）")
    for k, p in PLANS.items():
        e = [run(p, etf_ret=x, end_year=2046)[2046]['nw'] for x in (0, .04, .06, .08)]
        h = [run(p, house_g=x, end_year=2046)[2046]['nw'] for x in (-.01, .01, .02)]
        r46 = run(p, end_year=2046)[2046]
        stuck = run(p, end_year=2046, invest_cap=4)[2046]['nw']
        rent = sum(rents_of(p)) * (1 + HOUSE_G) ** 20
        print(f"  {k} " + " / ".join(f"{v:.0f}" for v in e) + "｜" + " / ".join(f"{v:.0f}" for v in h)
              + f"｜被動收入 {rent + r46['etf']*.04/12:.1f}｜剩餘房貸 {r46['debt']:.0f}｜一直停在每月 4 萬少 {e[2]-stuck:.0f}")


if __name__ == "__main__":
    main()
