"""一般糾結 v4（2026-09-28）
v3 + 兩點：
1) 穿插日多一種：K線實體明顯跨過均線（開盤與收盤分在均線兩側，而且兩者都離均線超過 0.1ATR）
1b) 整根K線（開高低收）都沒碰到均線＝明顯遠離均線，這天不算糾結的穿插
2) 警戒：糾結結束後 3 天內，若先有一天碰到均線（未穿插，最多一次）、接著又有穿插日 → 延續同一段糾結
v3 規則：穿插日看原本在均線哪一側（最近一次收盤離MA>0.1ATR）：原在下方→收盤明顯站上、或影線碰雜訊上緣但收盤沒站上；原在上方→反之。
  在原本那一側碰均線/進雜訊區＝回測，不算穿插。連續4天內≥3天穿插＝糾結；相鄰片段間隔≤3交易日接成同一段。
"""
import numpy as np
SV = 0.10
FAR = 1.5
def qualify(O, H, L, C, ma, mp, atr, x=.01, c=.015):
    N = len(C); q = np.zeros(N, bool); last = 0
    for t in range(1, N):
        if np.isnan(mp[t]) or np.isnan(atr[t]): continue
        d = C[t] - ma[t]; sv = SV * atr[t]
        side = 1 if d > sv else (-1 if d < -sv else 0)
        straddle = (O[t] - ma[t]) * (C[t] - ma[t]) < 0 and abs(O[t] - ma[t]) > sv and abs(C[t] - ma[t]) > sv   # 開盤與收盤分在均線兩側，且都離均線超過0.1ATR（肉眼可見的跨越）
        far = L[t] > ma[t] or H[t] < ma[t]     # 整根K線（開高低收）都沒碰到均線＝明顯遠離均線，不算糾結的穿插
        if last == -1:
            q[t] = (side == 1 and not far) or (H[t] >= mp[t] * (1 + x) and side != 1) or (straddle and not far)
        elif last == 1:
            q[t] = (side == -1 and not far) or (L[t] <= mp[t] * (1 - c) and side != -1) or (straddle and not far)
        if side: last = side
    return q
def detect(O, H, L, C, ma, mp, atr, gap=3):
    N = len(C); q = qualify(O, H, L, C, ma, mp, atr); spans = []
    for t in range(3, N):
        w = np.flatnonzero(q[t - 3:t + 1])
        if len(w) >= 3: spans.append((t - 3 + w[0], t - 3 + w[-1]))
    out = []
    for a, e in spans:
        if out and a - out[-1][1] <= gap: out[-1] = (out[-1][0], max(out[-1][1], e))
        else: out.append((a, e))
    # 警戒延續
    touch = (L <= ma) & (ma <= H)
    ext = []
    for a, e in out:
        k = e; warned = False
        while True:
            nxt = None
            for j in range(k + 1, min(k + 4, N)):
                if q[j]: nxt = j; break
                if touch[j]:
                    if warned: break
                    warned = True
            if nxt is None: break
            k = nxt
        if ext and a - ext[-1][1] <= gap: ext[-1] = (ext[-1][0], max(ext[-1][1], k))
        else: ext.append((a, k))
    return [(a, e, H[a:e + 1].max(), L[a:e + 1].min()) for a, e in ext]
