"""補跑：拆解用的兩個設定（pct_period_only、smooth_range_only）在截斷 21／63 根時的 final（finals_attr.csv）"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_eval as E, pandas as pd
from multiprocessing import Pool
def job(a):
    s, tk, p, cut = a; df = E.bars(p); df = df.iloc[:len(df) - cut].reset_index(drop=True); M = pd.read_pickle(f'{E.MD}/{tk}_{cut}.pkl'); rows = []
    for cfg in ('pct_period_only', 'smooth_range_only'):
        pm, sm = E.CONFIGS[cfg]; R = E.sel.select(df, E.score.score_table(M, E.REF, pct_mode=pm), smooth_mode=sm)
        for nm in R: rows.append(dict(set=s, ticker=tk, cut=cut, config=cfg, range=nm, final=R[nm]['final'], top=R[nm]['cands'][0]['均線']))
    return rows
if __name__ == '__main__':
    J = [(s, tk, p, c) for s, tk, p in E.stocks() for c in (21, 63)]
    with Pool(4) as P: rows = [r for rs in P.map(job, J, chunksize=2) for r in rs]
    pd.DataFrame(rows).to_csv(f'{E.OUT}/finals_attr.csv', index=False); print(len(rows))
