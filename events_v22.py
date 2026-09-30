"""事件判斷＋簡單策略模擬 v22（2026-09-29）— 多空反手版（停損反手 SAR）
狀態：多 / 空 / 空手（空手只出現在「假突破」之後或剛開始）
  訊號用雜訊邊界判斷（不再看收盤在均線哪一側）：上緣＝前一日均線×1.01；下緣＝前一日均線×0.985
  持有多單：碰到下緣 → 以 min(開盤, 下緣) 出場，並反手做空（進場價同出場價）；碰到上緣不算突破
  持有空單：碰到上緣 → 以 max(開盤, 上緣) 出場，並反手做多；碰到下緣不算跌破
  空手：碰到上緣 → 做多；碰到下緣 → 做空（兩邊都碰＝取離開盤較近的一邊）
  進場價＝max(開盤, 上緣)（多）／min(開盤, 下緣)（空）；進場當天不檢查出場，隔天起才檢查
  當天收盤明顯站到進場方向（離均線>0.1ATR）＝真突破，繼續持有
  當天收盤沒有＝影線假突破（×）：仍然反手進場，但以「當天收盤價」出清 → 變空手
  空手之後的第一個進場：若方向＝空手之前最後一個「真持有」的方向 → 記為回測進場（◆，偏回測反彈）；否則記為突破
突破事件成功／失敗：進場後碰到反向邊界前先到 +3%＝成功；同天都碰＝失敗
回測（持有同方向或空手時記錄；持有反方向時不記）：同 v21（換邊後曾收盤>上緣且整根K線最低>均線+0.1ATR，或同側≥5天；
  碰均線容差 0.1ATR；反彈K線；等進場；只有碰到反向邊界算失敗；每次回測後要再離開雜訊區一次）
每筆交易成本 0.1%
回傳：brk（突破事件）、wick（假突破）、rts（回測事件）、plog（持倉區間：進場日,出場日,方向,進場價,出場價,類型）、trades
"""
import numpy as np
SV = 0.10; RT = 0.10; COST = 0.001
def race(H, L, start, up, tgt, stop):
    for k in range(start, len(H)):
        hs = ((L[k] <= stop[k]) if up else (H[k] >= stop[k])) and k > start
        ht = (H[k] >= tgt) if up else (L[k] <= tgt)
        if ht and hs: return 0, k
        if ht: return 1, k
        if hs: return 0, k
    return -1, None
def events(O, H, L, C, ma, atr, x=.01, c=.015, tg=.03):
    N = len(C); mp = np.r_[np.nan, ma[:-1]]; U = mp * (1 + x); Lb = mp * (1 - c)
    brk, wick, rts, plog, trades = [], [], [], [], []
    pos = 0; tin = -1; ep = 0.; kind = 'B'; vis = 0; since = 0
    dep = {1: False, -1: False}; used5 = False; need = {1: False, -1: False}
    lastreal = 0; falseflat = False; rt = None
    def close_pos(t, xp):
        nonlocal pos
        plog.append((tin, t, pos, ep, xp, kind)); trades.append((tin, t, pos, (xp / ep - 1) * pos - COST, kind)); pos = 0
    for t in range(1, N):
        if np.isnan(mp[t]) or np.isnan(atr[t]): continue
        sv = SV * atr[t]; up = H[t] >= U[t]; dn = L[t] <= Lb[t]
        # 1) 出場／反手／進場
        cand = 0
        if pos == 1 and t > tin and dn: close_pos(t, min(O[t], Lb[t])); cand = -1
        elif pos == -1 and t > tin and up: close_pos(t, max(O[t], U[t])); cand = 1
        elif pos == 0:
            if up and dn: cand = 1 if abs(O[t] - U[t]) <= abs(O[t] - Lb[t]) else -1
            elif up: cand = 1
            elif dn: cand = -1
        if cand != 0:
            sg = cand; band = U[t] if sg == 1 else Lb[t]; e = max(O[t], band) if sg == 1 else min(O[t], band)
            ok = (C[t] > ma[t] + sv) if sg == 1 else (C[t] < ma[t] - sv)
            if not ok:
                wick.append(dict(t=t, up=sg == 1))
                trades.append((t, t, sg, (C[t] / e - 1) * sg - COST, 'F')); falseflat = True; rt = None
            else:
                isR = falseflat and sg == lastreal
                r, k = race(H, L, t, sg == 1, e * (1 + tg * sg), Lb if sg == 1 else U)
                if isR: rts.append(dict(t=t, up=sg == 1, state='進場', entry=t, e=e, res=r, exit=k, ex=False, origin='假突破後'))
                else:
                    d2 = t + 1 < N and ((C[t + 1] > C[t] and H[t + 1] > H[t]) if sg == 1 else (C[t + 1] < C[t] and L[t + 1] < L[t]))
                    brk.append(dict(t=t, up=sg == 1, e=e, res=r, exit=k, d2=d2, ex=False))
                pos = sg; tin = t; ep = e; kind = 'R' if isR else 'B'; lastreal = sg; falseflat = False; rt = None
        # 2) 回測狀態推進
        if rt is not None:
            sg, st, bday = rt
            if pos == -sg: rt = None
            elif (L[t] <= Lb[t]) if sg == 1 else (H[t] >= U[t]):
                rts.append(dict(t=st, up=sg == 1, state='失敗', res=0, ex=False)); rt = None
            elif bday is None:
                if t - st > 10: rts.append(dict(t=st, up=sg == 1, state='無效', res=-1, ex=False)); rt = None
                elif (C[t] > O[t] and C[t] > C[t - 1]) if sg == 1 else (C[t] < O[t] and C[t] < C[t - 1]): rt = (sg, st, t)
            if rt is not None and rt[2] is not None:
                sg, st, bday = rt
                if t - bday > 10: rts.append(dict(t=st, up=sg == 1, state='有效未進場', res=-1, ex=False)); rt = None
                elif (H[t] >= U[t]) if sg == 1 else (L[t] <= Lb[t]):
                    e = max(O[t], U[t]) if sg == 1 else min(O[t], Lb[t])
                    r, k = race(H, L, t, sg == 1, e * (1 + tg * sg), Lb if sg == 1 else U)
                    rts.append(dict(t=st, up=sg == 1, state='進場', entry=t, e=e, res=r, exit=k, ex=False))
                    if pos == 0: pos = sg; tin = t; ep = e; kind = 'R'; lastreal = sg; falseflat = False
                    rt = None
        # 3) 更新明顯側（只給回測用）
        d = C[t] - ma[t]; ns = 1 if d > sv else (-1 if d < -sv else 0)
        if ns and ns != vis: vis = ns; since = t; dep = {1: False, -1: False}; used5 = False; need = {1: False, -1: False}
        if vis and t - since >= 5 and not used5 and not need[vis]: dep[vis] = True; used5 = True
        if C[t] > U[t] and L[t] > ma[t] + sv: dep[1] = True; need[1] = False
        if C[t] < Lb[t] and H[t] < ma[t] - sv: dep[-1] = True; need[-1] = False
        # 4) 回測開始（方向：持倉方向，空手用明顯側）
        side = pos if pos != 0 else vis
        if rt is None and side != 0 and dep[side] and t > tin:
            sg = side; rtol = RT * atr[t]
            touch = (L[t] <= ma[t] + rtol) if sg == 1 else (H[t] >= ma[t] - rtol)
            hold = (C[t] >= ma[t] - sv) if sg == 1 else (C[t] <= ma[t] + sv)
            if touch and hold: rt = (sg, t, None); dep[sg] = False; need[sg] = True; used5 = True
    if pos != 0:
        plog.append((tin, N - 1, pos, ep, C[-1], kind)); trades.append((tin, N - 1, pos, (C[-1] / ep - 1) * pos - COST, kind))
    return brk, wick, rts, plog, trades
def summary(trades, N, W):
    tr = [x for x in trades if x[1] >= N - W]; r = np.array([x[3] for x in tr]) if tr else np.array([])
    if not len(r): return dict(n=0, tot=0., win=np.nan)
    return dict(n=len(r), tot=float(np.prod(1 + r) - 1), win=float((r > 0).mean()))
