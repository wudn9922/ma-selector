"""hysteresis 證據：封存的 100 檔美股（experiments/rescue_validation/raw_outputs/<TICKER>/bars.csv，不連網）模擬三次月更——
資料少 42 根 → 少 21 根 → 完整；每次用 core.recommend.recommend（production 流程，美股成本與美股基準），prev＝上一次的輸出。
同一次計算同時給出「有 hysteresis」（final）與「沒有」（computedFinal 與 prev 無關，等於不用 hysteresis 的結果），所以兩條鏈用同一批 metrics／分數／回測，差別只有 hysteresis。
另外用 HYST_POINTS ＝ 2.5／5／10 各跑一遍當敏感度（production 門檻維持 5.0，沒有因此調整）。
用法：python experiments/hysteresis/simulate.py [--workers 4]        → results.csv（逐檔逐區間逐次）＋ summary.csv ＋ 終端機摘要
      python experiments/hysteresis/simulate.py --summarize-only      → 只用 results.csv 重算 summary.csv"""
import argparse, os, sys
from multiprocessing import Pool
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from core import data, metrics, recommend as rec
HERE = Path(__file__).resolve().parent; RAW = ROOT / 'experiments' / 'rescue_validation' / 'raw_outputs'
CUTS = (42, 21, 0)          # 第 1、2、3 次月更的「少幾根」
THRS = (2.5, 5.0, 10.0)     # 5.0 ＝ production（rec.HYST_POINTS）；其餘只是敏感度
KEYS = ('short', 'medium', 'long')
REF = pd.read_parquet(ROOT / 'data' / 'reference.parquet')

def run_ticker(tk):
    df = data.load(RAW / tk / 'bars.csv'); orig = metrics.compute_metrics; cache = {}
    metrics.compute_metrics = lambda d, kind='SMA': cache.setdefault(len(d), orig(d, kind=kind))    # 同一檔同一個截斷只算一次 metrics（與 hysteresis 無關）
    rows = []
    try:
        for thr in THRS:
            rec.HYST_POINTS = thr; prev = None
            for run, cut in enumerate(CUTS, 1):
                r = rec.recommend(df.iloc[:len(df) - cut].reset_index(drop=True), REF, tk, prev=prev, window_mode='legacy_exit'); prev = r
                for g in r['ranges']:
                    by = {c['period']: c for c in g['candidates']}; fin, cmp_ = by[g['final']], by[g['computedFinal']]
                    rows.append(dict(thr=thr, ticker=tk, run=run, cut=cut, asof=r['asof'], range=g['key'], final=g['final'], computed=g['computedFinal'], held=g['held'], previous=g['previousFinal'],
                                     score_final=fin['score'], score_computed=cmp_['score'], sar_final=fin['sarReturn'], sar_computed=cmp_['sarReturn'], unsuitable=g['unsuitable']))
    finally: metrics.compute_metrics = orig; rec.HYST_POINTS = 5.0
    return rows

def summarize(D):
    out = []
    for thr, X in D.groupby('thr'):
        for key in KEYS + ('all',):
            Y = X if key == 'all' else X[X['range'] == key]
            P = {run: Y[Y.run == run].set_index('ticker') for run in (1, 2, 3)}; row = dict(thr=thr, range=key, n=len(P[1]))
            ch_with, ch_without, only_with = [], [], 0
            for a, b in ((1, 2), (2, 3)):
                if key == 'all':   # 三個區間合併：用 (ticker, range) 當索引
                    A = Y[Y.run == a].set_index(['ticker', 'range']); B = Y[Y.run == b].set_index(['ticker', 'range'])
                else: A, B = P[a], P[b]
                w = (B.final != A.final.reindex(B.index)).to_numpy(); wo = (B.computed != A.computed.reindex(B.index)).to_numpy()
                row[f'chg_with_{a}to{b}'] = w.mean(); row[f'chg_without_{a}to{b}'] = wo.mean(); ch_with.append(w); ch_without.append(wo); only_with += int((w & ~wo).sum())
            row['chg_with_pooled'] = np.concatenate(ch_with).mean(); row['chg_without_pooled'] = np.concatenate(ch_without).mean(); row['only_with_changes'] = only_with
            A1 = Y[Y.run == 1].set_index(['ticker', 'range']); A3 = Y[Y.run == 3].set_index(['ticker', 'range'])
            row['chg_with_1to3'] = (A3.final != A1.final.reindex(A3.index)).mean(); row['chg_without_1to3'] = (A3.computed != A1.computed.reindex(A3.index)).mean()
            R = Y[Y.run > 1]; H = R[R.held]; row['held_rate'] = R.held.mean(); row['n_held'] = len(H)
            row['gap_score_mean'] = (H.score_computed - H.score_final).mean() if len(H) else np.nan; row['gap_score_max'] = (H.score_computed - H.score_final).max() if len(H) else np.nan
            row['gap_sar_mean_pp'] = 100 * (H.sar_final - H.sar_computed).mean() if len(H) else np.nan      # 沿用的 final 比新算的 final 的反手報酬多（＋）／少（−）幾個百分點
            row['unsuitable_run3'] = Y[Y.run == 3].unsuitable.mean()
            out.append(row)
    return pd.DataFrame(out)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--workers', type=int, default=os.cpu_count() or 1); ap.add_argument('--summarize-only', action='store_true'); a = ap.parse_args()
    if not a.summarize_only:
        tks = sorted(p.name for p in RAW.iterdir() if p.is_dir()); print(f'{len(tks)} 檔 × {len(CUTS)} 次 × {len(THRS)} 個門檻', flush=True)
        with Pool(a.workers) as p: rows = [r for rs in p.imap_unordered(run_ticker, tks) for r in rs]
        pd.DataFrame(rows).sort_values(['thr', 'ticker', 'run', 'range']).to_csv(HERE / 'results.csv', index=False)
    D = pd.read_csv(HERE / 'results.csv'); S = summarize(D); S.to_csv(HERE / 'summary.csv', index=False, float_format='%.4f')
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30); print(S.round(3).to_string(index=False))

if __name__ == '__main__': main()
