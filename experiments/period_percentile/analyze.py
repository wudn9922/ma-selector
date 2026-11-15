"""finals.csv → 報告用的彙總表（edge、分佈、穩定度、old→new）＋ 無趨勢虛無模型（符號隨機的隨機漫步）下的邊界比例"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, ROOT)
import numpy as np, pandas as pd
from core import score, select as sel
OUT = os.path.dirname(os.path.abspath(__file__)); MD = os.environ.get('PP_CACHE') or os.path.join(tempfile.gettempdir(), 'period_percentile_M'); D = pd.concat([pd.read_csv(f'{OUT}/finals.csv'), pd.read_csv(f'{OUT}/finals_attr.csv')], ignore_index=True)   # finals_attr＝拆解用兩個設定在截斷 21／63 根的 final
RG = {nm: (lo, hi) for nm, lo, hi, _ in sel.RANGES}; CFG = ['OLD', 'NEW_period', 'NEW_band', 'pct_period_only', 'smooth_range_only']
def pct(x): return f'{100 * x:.1f}%'
rows = []
for cfg in CFG:
    for nm, (lo, hi) in RG.items():
        x = D[(D.config == cfg) & (D.cut == 0) & (D.range == nm)]; f = x.final; t = x.top; n = len(x); L = hi - lo + 1; th = L / 3
        rows.append(dict(config=cfg, range=nm, n=n, uniform=1 / L, final_lo=(f == lo).mean(), final_hi=(f == hi).mean(), final_edge=((f == lo) | (f == hi)).mean(),
                         final_lo3=(f <= lo + 2).mean(), final_hi3=(f >= hi - 2).mean(), third1=(f < lo + th).mean(), third2=((f >= lo + th) & (f < lo + 2 * th)).mean(), third3=(f >= lo + 2 * th).mean(),
                         median=f.median(), q1=f.quantile(.25), q3=f.quantile(.75), mean=f.mean(), top_lo=(t == lo).mean(), top_hi=(t == hi).mean()))
E = pd.DataFrame(rows); E.to_csv(f'{OUT}/edge_summary.csv', index=False)
# 逐週期分佈
H = D[D.cut == 0].groupby(['config', 'range', 'final']).size().rename('n').reset_index(); H.to_csv(f'{OUT}/final_distribution.csv', index=False)
# 穩定度
st = []
for cfg in CFG:
    b = D[(D.config == cfg) & (D.cut == 0)].set_index(['ticker', 'range']).final
    for cut in (21, 63):
        c = D[(D.config == cfg) & (D.cut == cut)].set_index(['ticker', 'range']).final.reindex(b.index); d = (c - b).abs()
        for nm in RG:
            k = d.xs(nm, level='range'); ch = k[k > 0]
            st.append(dict(config=cfg, cut=cut, range=nm, n=len(k), changed=len(ch), share=len(ch) / len(k), median_abs_delta=ch.median() if len(ch) else 0, mean_abs_delta=k.mean()))
ST = pd.DataFrame(st); ST.to_csv(f'{OUT}/stability.csv', index=False)
# 成對：OLD vs NEW 誰變（McNemar 計數）
pair = []
for new in ('NEW_period', 'NEW_band'):
    for cut in (21, 63):
        for nm in RG:
            def chg(cfg):
                b = D[(D.config == cfg) & (D.cut == 0) & (D.range == nm)].set_index('ticker').final; c = D[(D.config == cfg) & (D.cut == cut) & (D.range == nm)].set_index('ticker').final.reindex(b.index); return b != c
            o, w = chg('OLD'), chg(new); pair.append(dict(new=new, cut=cut, range=nm, both=int((o & w).sum()), old_only=int((o & ~w).sum()), new_only=int((~o & w).sum()), neither=int((~o & ~w).sum())))
PR = pd.DataFrame(pair); PR.to_csv(f'{OUT}/stability_paired.csv', index=False)
# old → new
on = []
for new in ('NEW_period', 'NEW_band', 'pct_period_only', 'smooth_range_only'):
    a = D[(D.config == 'OLD') & (D.cut == 0)].set_index(['ticker', 'range']).final; b = D[(D.config == new) & (D.cut == 0)].set_index(['ticker', 'range']).final.reindex(a.index); d = (b - a)
    for nm in RG:
        k = d.xs(nm, level='range'); ch = k[k != 0]
        on.append(dict(new=new, range=nm, n=len(k), changed=len(ch), share=len(ch) / len(k), median_abs=ch.abs().median() if len(ch) else 0, le2=int((ch.abs() <= 2).sum()), d3_5=int(((ch.abs() >= 3) & (ch.abs() <= 5)).sum()),
                       d6_10=int(((ch.abs() >= 6) & (ch.abs() <= 10)).sum()), gt10=int((ch.abs() > 10).sum()), mean_signed=ch.mean() if len(ch) else 0))
ON = pd.DataFrame(on); ON.to_csv(f'{OUT}/old_vs_new.csv', index=False)
# 無趨勢虛無模型：每檔、每區間，用 NEW_period 未平滑分數的相鄰差 |Δ|，隨機排列＋隨機正負號 → 累加 → 區間內平滑 → argmax 落在兩端的比例
REF = pd.read_parquet(f'{ROOT}/data/reference.parquet'); rng = np.random.default_rng(0); null = {nm: [0, 0, 0] for nm in RG}; obs_inc = []
for tk in sorted(D[D.cut == 0].ticker.unique()):
    M = pd.read_pickle(f'{MD}/{tk}_0.pkl'); S = score.score_table(M, REF).sort_values('period'); P = S.period.to_numpy(); s = S['分數'].to_numpy()
    for nm, (lo, hi) in RG.items():
        v = s[(P >= lo) & (P <= hi)]; inc = np.abs(np.diff(v)); obs_inc.append(dict(range=nm, ticker=tk, lag1_autocorr=np.corrcoef(v[:-1], v[1:])[0, 1]))
        for _ in range(200):
            w = np.r_[0, np.cumsum(rng.permutation(inc) * rng.choice((-1, 1), len(inc)))]; i = int(np.argmax(sel.smooth(w)))
            null[nm][0] += i == 0; null[nm][1] += i == len(w) - 1; null[nm][2] += 1
iid = {}
for nm, (lo, hi) in RG.items():   # 對照：獨立雜訊（沒有任何週期趨勢、沒有自相關）經同一個兩端補自己的 3 點平滑後，argmax 落在兩端的比例
    L = hi - lo + 1; e = np.array([np.argmax(sel.smooth(rng.normal(size=L))) for _ in range(20000)]); iid[nm] = ((e == 0).mean(), (e == L - 1).mean())
NU = pd.DataFrame([dict(range=nm, uniform=1 / (RG[nm][1] - RG[nm][0] + 1), iid_top_lo=iid[nm][0], iid_top_hi=iid[nm][1], null_top_lo=a / n, null_top_hi=b / n) for nm, (a, b, n) in null.items()]); NU.to_csv(f'{OUT}/null_edge.csv', index=False)
AC = pd.DataFrame(obs_inc).groupby('range').lag1_autocorr.median()
with pd.option_context('display.width', 250, 'display.max_columns', 30):
    print(E.round(3).to_string()); print(ST.round(3).to_string()); print(PR.to_string()); print(ON.round(2).to_string()); print(NU.round(3).to_string()); print('lag1 autocorr of score within range (median):', AC.round(3).to_dict())
