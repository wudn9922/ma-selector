"""A3 評估：OLD（pooled＋whole）vs NEW（period／band＋range）在封存 bars 上的 final 分佈、截斷穩定度、old→new 改變。
輸出 finals.csv（每 ticker×cut×config×range 一列）。M 先算好存 pickle（PP_CACHE）。基準＝repo 的 data/reference.parquet（三個截斷點用同一份）。
用法：python experiments/period_percentile/run_eval.py；再跑 run_eval_attr.py、analyze.py"""
import glob, os, sys, time, tempfile
from multiprocessing import Pool
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, ROOT)
import numpy as np, pandas as pd
from core import data, metrics, score, select as sel
OUT = os.path.dirname(os.path.abspath(__file__)); MD = os.environ.get('PP_CACHE') or os.path.join(tempfile.gettempdir(), 'period_percentile_M')   # 指標快取（pickle，不進 repo）
os.makedirs(MD, exist_ok=True)
REF = pd.read_parquet(f'{ROOT}/data/reference.parquet')
CUTS = (0, 21, 63)
CONFIGS = {'OLD': ('pooled', 'whole'), 'NEW_period': ('period', 'range'), 'NEW_band': ('band', 'range'),
           'pct_period_only': ('period', 'whole'), 'smooth_range_only': ('pooled', 'range')}
SETS = {'fresh100': f'{ROOT}/experiments/rescue_validation/raw_outputs', 'holdout8': f'{ROOT}/experiments/holdout_v22/raw_outputs'}

def bars(path):
    return data.normalize(pd.read_csv(path, float_precision='round_trip'))

def stocks():
    out = []
    for s, d in SETS.items():
        for p in sorted(glob.glob(d + '/*/bars.csv')): out.append((s, p.split('/')[-2], p))
    return out

def job_M(a):
    s, tk, p, cut = a; f = f'{MD}/{tk}_{cut}.pkl'
    if not os.path.exists(f):
        df = bars(p); df = df.iloc[:len(df) - cut].reset_index(drop=True); metrics.compute_metrics(df).to_pickle(f)
    return f

def job_sel(a):
    s, tk, p, cut = a; df = bars(p); df = df.iloc[:len(df) - cut].reset_index(drop=True); M = pd.read_pickle(f'{MD}/{tk}_{cut}.pkl'); rows = []
    for cfg, (pm, sm) in CONFIGS.items():
        if cut and cfg in ('pct_period_only', 'smooth_range_only'): continue
        S = score.score_table(M, REF, pct_mode=pm); R = sel.select(df, S, smooth_mode=sm, window_mode='legacy_exit')
        for nm, lo, hi, _W in sel.RANGES:
            r = R[nm]; f = next(c for c in r['cands'] if c['均線'] == r['final'])
            rows.append(dict(set=s, ticker=tk, cut=cut, config=cfg, range=nm, final=r['final'], top=r['cands'][0]['均線'], cands=' '.join(str(c['均線']) for c in r['cands']),
                             best=float(r['cands'][0]['結構分']), final_score=f['結構分'], final_sar=f['反手報酬'], best_sar=max(c['反手報酬'] for c in r['cands']), n_bars=len(df)))
    return rows

if __name__ == '__main__':
    t = time.time(); J = [(s, tk, p, c) for s, tk, p in stocks() for c in CUTS]; print(len(J), 'jobs', flush=True)
    with Pool(4) as P: P.map(job_M, J, chunksize=2)
    print('M done', round(time.time() - t), flush=True)
    with Pool(4) as P: rows = [r for rs in P.map(job_sel, J, chunksize=2) for r in rs]
    pd.DataFrame(rows).to_csv(f'{OUT}/finals.csv', index=False); print('done', len(rows), round(time.time() - t), flush=True)
