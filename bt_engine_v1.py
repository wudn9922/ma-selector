"""均線策略回測引擎 v1（2026-09-29）— 網頁回測功能的核心
v1 變更：只做多（預設 longonly=True）；加入回測進場（多方，retest=True）；尾倉（≤20%）遇到反向訊號只平倉、不反手
回測規則（多方）：明顯側在上方；換邊後曾「收盤>上緣且整根K線最低>均線+0.1ATR」或已在上方≥5天；
  當天最低 ≤ 均線+0.1ATR 且收盤沒明顯跌破（≥均線−0.1ATR）→ 回測開始；之後出現反彈K線（收紅且收盤>前一天）→
  碰到前一日均線×1.01 進場；等待期間只有碰到下緣才算失敗（最多等20天）
以下為 v0 說明：
共同：肉眼可見 SV=0.1ATR；雜訊區 上緣=前日MA×(1+x)、下緣=前日MA×(1−c)；觸發=最近一根明顯收盤在另一側、今天影線碰雜訊邊界
　　　進場價=邊界價（跳空越過用開盤）；每筆以「初始資金1」計（不複利），扣成本 cost（單邊）
簡單策略：碰到雜訊邊界進場；碰到反向雜訊邊界出場（當天收盤沒站上均線＝影線假突破，收盤出場）
複雜策略：
　進場後早退（可各自開關）：①進場當天收盤收回均線（沒明顯站上）→收盤出場 ②隔天二日法則不成立→隔天收盤出場 ③進場當天沒有量增(≥前日×1.1)→收盤出場
　獲利 +tp（預設3%）→ 出清一半，止損移到成本價（損益兩平）
　之後每逢急漲（當日漲幅≥surge_pct 或 ≥surge_atr×ATR）→ 收盤出清初始部位的 10%，直到只剩初始的 20%
　出場：碰到反向雜訊邊界 → 出清現有部位一半；之後價格再創新低（跌破那天最低點）→ 全部出清
其他時候持倉期間不開新倉
輸出：總報酬（複利、每筆全額）、最大回撤、勝率、交易筆數（區間內出場的交易，含區間前進場者）、獲利因子、平均賺賠、每筆明細
"""
import numpy as np
SV = 0.10
def _side(C, ma, atr, t):
    d = C[t] - ma[t]; s = SV * atr[t]
    return 1 if d > s else (-1 if d < -s else 0)
def run(O, H, L, C, V, ma, atr, lo=0, x=.01, c=.015, cost=.001, mode='simple', longonly=True, retest=True,
        tp=.03, surge_pct=.05, surge_atr=1.5, ex_close=True, ex_day2=True, ex_vol=False):
    N = len(C); mp = np.r_[np.nan, ma[:-1]]; U = mp * (1 + x); Lb = mp * (1 - c)
    eq = np.ones(N); cap = 1.; trades = []; last = 0; since = 0; dep = False; rt = None; kind = 'B'
    pos = 0; size = 0.; e = 0.; tin = 0; realized = 0.; tp_done = False; be = False; half_low = None
    def close_part(frac, price):
        nonlocal size, realized
        q = min(frac, size); realized += q * ((price / e - 1) * pos - cost); size -= q
    for t in range(1, N):
        if np.isnan(mp[t]) or np.isnan(atr[t]):
            eq[t] = cap; continue
        if pos != 0 and t > tin:
            sg = pos
            if mode == 'simple':
                stop = Lb[t] if sg == 1 else U[t]
                if (L[t] <= stop) if sg == 1 else (H[t] >= stop):
                    close_part(size, min(O[t], stop) if sg == 1 else max(O[t], stop))
            else:
                if ex_day2 and t == tin + 1:
                    ok = (C[t] > C[t - 1] and H[t] > H[t - 1]) if sg == 1 else (C[t] < C[t - 1] and L[t] < L[t - 1])
                    if not ok: close_part(size, C[t])
                if size > 0 and not tp_done:
                    tgt = e * (1 + tp * sg)
                    if (H[t] >= tgt) if sg == 1 else (L[t] <= tgt):
                        close_part(0.5, tgt); tp_done = True; be = True
                if size > 0 and be:
                    if (L[t] <= e) if sg == 1 else (H[t] >= e): close_part(size, e)
                if size > 0 and tp_done:
                    chg = (C[t] / C[t - 1] - 1) * sg; rng_ = (C[t] - C[t - 1]) * sg
                    if (chg >= surge_pct or rng_ >= surge_atr * atr[t]) and size > 0.2 + 1e-9:
                        close_part(min(0.1, size - 0.2), C[t])
                if size > 0:
                    if half_low is not None and ((L[t] < half_low) if sg == 1 else (H[t] > half_low)):
                        close_part(size, half_low if sg == 1 else half_low)
                    else:
                        stop = Lb[t] if sg == 1 else U[t]
                        if half_low is None and ((L[t] <= stop) if sg == 1 else (H[t] >= stop)):
                            close_part(size / 2, min(O[t], stop) if sg == 1 else max(O[t], stop))
                            half_low = L[t] if sg == 1 else H[t]
            if size <= 1e-9:
                if t >= lo: trades.append(dict(tin=tin, tout=t, side=pos, ret=realized, kind=kind))
                cap *= (1 + realized) if t >= lo else 1; pos = 0; size = 0.
        # 只剩尾倉（≤20%）時遇到反向訊號 → 平掉尾倉（不反手）
        if pos != 0 and size <= 0.2 + 1e-9 and t > tin:
            opp = -pos; band2 = U[t] if opp == 1 else Lb[t]
            opp_sig = last == -opp and ((H[t] >= band2) if opp == 1 else (L[t] <= band2)) and ((C[t] > ma[t] + SV * atr[t]) if opp == 1 else (C[t] < ma[t] - SV * atr[t]))
            if opp_sig:
                close_part(size, max(O[t], band2) if opp == 1 else min(O[t], band2))   # 只平倉，不反手
                if t >= lo: trades.append(dict(tin=tin, tout=t, side=pos, ret=realized, kind=kind))
                cap *= (1 + realized) if t >= lo else 1; pos = 0; size = 0.
        # 回測狀態（多方）
        if retest and pos == 0 and rt is not None:
            st, bounced = rt
            if t - st > 20 or L[t] <= Lb[t]: rt = None
            elif not bounced:
                if C[t] > O[t] and C[t] > C[t - 1]: rt = (st, True)
            elif H[t] >= U[t]:
                pos = 1; size = 1.; e = max(O[t], U[t]); tin = t; kind = 'R'
                realized = 0.; tp_done = False; be = False; half_low = None; rt = None
                if mode == 'complex' and H[t] >= e * (1 + tp): close_part(0.5, e * (1 + tp)); tp_done = True; be = True
        # 進場
        if pos == 0:
            for sg in (1, -1):
                if longonly and sg == -1: continue
                band = U[t] if sg == 1 else Lb[t]
                if last == -sg and ((H[t] >= band) if sg == 1 else (L[t] <= band)):
                    pos = sg; size = 1.; e = max(O[t], band) if sg == 1 else min(O[t], band); tin = t; kind = 'B'; rt = None
                    realized = 0.; tp_done = False; be = False; half_low = None
                    wick = not ((C[t] > ma[t] + SV * atr[t]) if sg == 1 else (C[t] < ma[t] - SV * atr[t]))
                    volok = V[t - 1] > 0 and V[t] >= 1.1 * V[t - 1]
                    if mode == 'simple':
                        if wick: close_part(1., C[t])
                    else:
                        if (ex_close and wick) or (ex_vol and not volok): close_part(1., C[t])
                        elif size > 0 and ((H[t] >= e * (1 + tp)) if sg == 1 else (L[t] <= e * (1 - tp))):
                            close_part(0.5, e * (1 + tp * sg)); tp_done = True; be = True
                    if size <= 1e-9:
                        if t >= lo: trades.append(dict(tin=tin, tout=t, side=pos, ret=realized, kind=kind))
                        cap *= (1 + realized) if t >= lo else 1; pos = 0; size = 0.
                    break
        s = _side(C, ma, atr, t)
        if s and s != last: last = s; since = t; dep = False; rt = None
        if last == 1 and C[t] > U[t] and L[t] > ma[t] + SV * atr[t]: dep = True
        if last == 1 and t - since >= 5: dep = True
        if retest and pos == 0 and rt is None and last == 1 and dep and L[t] <= ma[t] + SV * atr[t] and C[t] >= ma[t] - SV * atr[t]:
            rt = (t, False); dep = False
        eq[t] = cap * (1 + (realized + size * ((C[t] / e - 1) * pos) if pos else 0)) if t >= lo else 1.
    if pos != 0:
        close_part(size, C[-1]); trades.append(dict(tin=tin, tout=N - 1, side=pos, ret=realized, open=True, kind=kind)); cap *= (1 + realized)
    seg = eq[lo:]
    peak = np.maximum.accumulate(seg); mdd = float((seg / peak - 1).min())
    r = np.array([tr['ret'] for tr in trades]) if trades else np.array([])
    w = r[r > 0]; l = r[r <= 0]
    return dict(總報酬=float(cap - 1), 最大回撤=mdd, 勝率=float((r > 0).mean()) if len(r) else np.nan,
                筆數=len(r), 獲利因子=float(w.sum() / -l.sum()) if l.sum() < 0 else np.inf,
                平均賺=float(w.mean()) if len(w) else 0., 平均賠=float(l.mean()) if len(l) else 0.), trades
