"""離線代理檢查（不是 final 命中率）：開發集 83 檔 asof 2026-09-24 的 frozen 指標（diagnostics/old_composite.csv.gz）
→ 基準＝這 83 檔自己（同 production_sanity）→ OLD／NEW 的候選集合（gap 15、彼此差 >2、最多 5 條；不需回測）與結構分第一名，對人工線算命中。
final（規則 B＋rescue）需要反手回測＝需要 bars，開發集 bars 不在 repo 內 → 這裡算不出來。"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path[:0] = [ROOT, ROOT + '/scripts', ROOT + '/research']
import numpy as np, pandas as pd
from core import score, select as sel
import regression as R
OUT = os.path.dirname(os.path.abspath(__file__))
D = pd.read_csv(f'{ROOT}/diagnostics/old_composite.csv.gz')
print(D.ticker.nunique(), D.groupby('ticker').size().unique())
F = score.make_features(D); F['ticker'] = D['ticker'].to_numpy(); REF = F
MODES = {'OLD': ('pooled', 'whole'), 'NEW_period': ('period', 'range'), 'NEW_band': ('band', 'range')}
def cands(P, Ss, lo, hi, gap=sel.GAP):
    m = (P >= lo) & (P <= hi); pm, sm = P[m], Ss[m]; o = np.argsort(-sm); best = sm[o[0]]; out = []
    for i in o:
        if sm[i] < best - gap: break
        if all(abs(pm[i] - c) > 2 for c in out): out.append(int(pm[i]))
        if len(out) == 5: break
    return out
rows = []
for cfg, (pm, smm) in MODES.items():
    for tk, g in D.groupby('ticker', sort=False):
        M = g.sort_values('period').reset_index(drop=True); S = score.score_table(M, REF, pct_mode=pm); P, Ss = sel.smoothed_scores(S, smm)
        for nm, lo, hi, _ in sel.RANGES:
            c = cands(P, Ss, lo, hi); u = [p for p in R.USER.get(tk, []) if lo <= p <= hi]
            rows.append(dict(config=cfg, ticker=tk, range=nm, user=' '.join(map(str, u)), cands=' '.join(map(str, c)), top=c[0], n_user=len(u)))
T = pd.DataFrame(rows); T.to_csv(f'{OUT}/label_proxy.csv', index=False)
# 驗證代理：OLD 的短期候選應等於 regression/candidate_hit_rate.csv 的 old_candidates（research final_select 的候選，同一份 frozen 指標）
H = pd.read_csv(f'{ROOT}/regression/candidate_hit_rate.csv'); H = H[H.ticker != '__TOTAL__']
o = T[T.config == 'OLD'].set_index(['ticker', 'range'])
chk = [(r.ticker, r.range, str(r.old_candidates), o.loc[(r.ticker, r.range), 'cands']) for r in H.itertuples() if (r.ticker, r.range) in o.index]
same = sum(a == b for _, _, a, b in chk); print(f'OLD 代理候選 vs regression old_candidates（研究版 final_select）：{same}/{len(chk)} 相同（集合相同 {sum(set(a.split()) == set(b.split()) for _, _, a, b in chk)}）')
for t, r_, a, b in chk:
    if a != b: print('  diff', t, r_, a, '|', b)
for nm, tol in (('短期', 2), ('中期', 2), ('長期', 5)):
    for cfg in MODES:
        x = T[(T.config == cfg) & (T.range == nm) & (T.n_user > 0)]
        ch = sum(any(abs(int(p) - int(c)) <= tol for p in r.user.split() for c in r.cands.split()) for r in x.itertuples())
        th = sum(any(abs(int(p) - r.top) <= tol for p in r.user.split()) for r in x.itertuples())
        print(nm, f'±{tol}', cfg, f'cand {ch}/{len(x)}  top {th}/{len(x)}  mean#cands {x.cands.str.split().str.len().mean():.2f}')
