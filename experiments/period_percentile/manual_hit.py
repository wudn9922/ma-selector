"""同週期百分位＋區間內平滑：開發集 83 檔人工線命中率（OLD vs NEW）。需要連 Yahoo（開發集 bars 沒有封存在 repo）；本機無法連線時只能用 --synthetic 做流程測試。
條件同 production_sanity／selector_v2 診斷：asof 2026-09-24、基準＝這批股票自己（make_features 後當 reference）。人工標記也被用來開發現行規則 → 只是診斷，不是驗證。
OLD＝score_table(pct_mode='pooled')＋select(smooth_mode='whole')（改動前的 production）；NEW＝production 預設（pct_mode='period'＋smooth_mode='range'）；BAND＝pct_mode='band'＋range（比較用）
命中：短期／中期 final 距人工線 ≤2、長期 ≤5（另列 ≤2）；候選命中同容差；15–45 兩條（短期 final＋中期 final）取較近 ≤2（同 diag_report.md 的「現行 兩條」口徑）
用法：python experiments/period_percentile/manual_hit.py [--asof 2026-09-24] [--out experiments/period_percentile/manual_hit] [--synthetic] [--only A,B]"""
import argparse, os, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
import regression as R
from core import data, metrics, score, select as sel
from core.universe import TICKERS
CONFIGS = {'OLD': ('pooled', 'whole'), 'NEW': ('period', 'range'), 'BAND': ('band', 'range')}
TOL = {'短期': 2, '中期': 2, '長期': 5}
ADJ = 'NEW_ADJ'   # NEW 模式＋還原股利的價格（production 抓價的預設）；基準＝還原後的這批股票自己。人工線是在未還原的圖上標的

def fetch_adj(a):
    tk, wd, asof, synthetic = a; src = Path(wd) / 'data_v' / f'{tk}.csv'; dst = Path(wd) / 'data_adj' / f'{tk}.csv'
    if synthetic: dst.write_bytes(src.read_bytes()); return tk, None, False      # 合成資料沒有股利：只走流程
    err = None
    for k in range(4):
        try: df = data.normalize(data.fetch_yahoo(tk, adjust=True), asof); break
        except Exception as e: err = e; time.sleep(2 * (k + 1))
    else: return tk, str(err), False
    df.drop(columns='date').to_csv(dst, index=False); return tk, None, bool(df.attrs.get('adjusted', False))

def adj_metrics(a):
    tk, asof = a; return tk, metrics.compute_metrics(data.normalize(pd.read_csv(f'data_adj/{tk}.csv'), asof))

def run_adj(a):
    tk, asof, ref = a; df = data.normalize(pd.read_csv(f'data_adj/{tk}.csv'), asof)
    return tk, sel.select(df, score.score_table(M_ADJ[tk], ref))                 # production 預設（period＋range）

def run_one(a):
    tk, asof, ref = a
    df = data.normalize(pd.read_csv(f'data_v/{tk}.csv'), asof); M = M_ALL[tk]
    return tk, {c: sel.select(df, score.score_table(M, ref, pct_mode=pm), smooth_mode=sm) for c, (pm, sm) in CONFIGS.items()}

def near(x, us): return min(abs(x - u) for u in us) if us else np.nan

def main():
    global M_ALL, M_ADJ
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='experiments/period_percentile/manual_hit'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='mhit_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True); (wd / 'data_adj').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True)
    if not tks: sys.exit('沒有任何資料（Yahoo 無法連線？）—— 本檢查沒有執行')
    with ProcessPoolExecutor(4) as ex: adj = list(ex.map(fetch_adj, [(t, str(wd), a.asof, a.synthetic) for t in tks]))
    atks = [t for t, e, _ in adj if not e]; n_adj = sum(1 for _t, e, ok in adj if not e and ok); fails += [(f'{t}（還原股利）', e) for t, e, _ in adj if e]
    os.chdir(wd)
    with ProcessPoolExecutor(4) as ex: M_ALL = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in M_ALL.items()], ignore_index=True)
    with ProcessPoolExecutor(4) as ex: res = dict(ex.map(run_one, [(tk, a.asof, ref) for tk in tks]))
    with ProcessPoolExecutor(4) as ex: M_ADJ = dict(ex.map(adj_metrics, [(tk, a.asof) for tk in atks]))
    ref_adj = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in M_ADJ.items()], ignore_index=True) if atks else None
    with ProcessPoolExecutor(4) as ex: radj = dict(ex.map(run_adj, [(tk, a.asof, ref_adj) for tk in atks]))
    for tk, x in radj.items(): res[tk][ADJ] = x
    CF = list(CONFIGS) + [ADJ]
    rows = []
    for tk in tks:
        u = R.USER.get(tk, [])
        for nm, lo, hi, _W in sel.RANGES:
            us = [p for p in u if lo <= p <= hi]; r = dict(ticker=tk, range=nm, user=' '.join(map(str, us)), n_user=len(us))
            for c in CF:
                if c not in res[tk]: r.update({f'{c}_final': np.nan, f'{c}_cands': '', f'{c}_d': np.nan, f'{c}_cand_hit': np.nan}); continue
                x = res[tk][c][nm]; cs = [k['均線'] for k in x['cands']]
                r.update({f'{c}_final': x['final'], f'{c}_cands': ' '.join(map(str, cs)), f'{c}_d': near(x['final'], us), f'{c}_cand_hit': any(abs(p - k) <= TOL[nm] for p in us for k in cs) if us else np.nan})
            rows.append(r)
        us = [p for p in u if 15 <= p <= 45]
        r = dict(ticker=tk, range='15–45 兩條', user=' '.join(map(str, us)), n_user=len(us))
        for c in CF: r[f'{c}_d'] = min(near(res[tk][c]['短期']['final'], us), near(res[tk][c]['中期']['final'], us)) if us and c in res[tk] else np.nan
        rows.append(r)
    T = pd.DataFrame(rows); T.to_csv(out / 'manual_hit.csv', index=False)
    L = [f'# 人工線命中（開發集 {len(tks)} 檔，asof {a.asof}，基準＝這批股票自己{"，**合成資料：流程測試，不是結果**" if a.synthetic else ""}）\n',
         '人工標記也被用來開發現行規則，所以這裡只是診斷，不是驗證。OLD＝改動前 production（pooled＋whole）；NEW＝新 production 預設（period＋range）；BAND＝鄰近週期 ±2（比較用）；' + f'NEW_ADJ＝NEW＋還原股利的價格（{len(atks)} 檔取得、其中 {n_adj} 檔實際有還原；基準＝還原後的這批股票自己）。人工線是在未還原的圖上標的。\n',
         '| 區間 | 有人工線檔數 | 容差 | ' + ' | '.join(f'{c} final 命中' for c in CF) + ' | ' + ' | '.join(f'{c} 平均距離' for c in CF) + ' | ' + ' | '.join(f'{c} 候選命中' for c in CF) + ' |',
         '|---|---|---|' + '---|' * (3 * len(CF))]
    for nm in ('短期', '中期', '長期', '15–45 兩條'):
        for tol in ((TOL.get(nm, 2),) if nm != '長期' else (5, 2)):
            x = T[(T.range == nm) & (T.n_user > 0)]; n = len(x)
            hit = [f"{int((x[f'{c}_d'] <= tol).sum())}/{n}" for c in CF]; dist = [f"{x[f'{c}_d'].mean():.2f}" if n else '—' for c in CF]
            ch = [f"{int((x[f'{c}_cand_hit'] == True).sum())}/{n}" if f'{c}_cand_hit' in x and nm != '15–45 兩條' and tol == TOL.get(nm, 2) else '—' for c in CF]
            L.append(f'| {nm} | {n} | ±{tol} | ' + ' | '.join(hit) + ' | ' + ' | '.join(dist) + ' | ' + ' | '.join(ch) + ' |')
    x = T[T.range != '15–45 兩條']; L.append('\nfinal old→new 改變：' + '、'.join(f"{nm} {int((x[x.range == nm].OLD_final != x[x.range == nm].NEW_final).sum())}/{int((x.range == nm).sum())}" for nm, *_ in sel.RANGES))
    L.append('final NEW→NEW_ADJ（還原股利）改變：' + '、'.join(f"{nm} {int((x[x.range == nm].NEW_final != x[x.range == nm][ADJ + '_final']).sum())}/{int((x.range == nm).sum())}" for nm, *_ in sel.RANGES))
    if fails: L.append('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails))
    (out / 'manual_hit.md').write_text('\n'.join(L) + '\n', encoding='utf-8'); print('\n'.join(L))

M_ALL = {}; M_ADJ = {}
if __name__ == '__main__': main()
