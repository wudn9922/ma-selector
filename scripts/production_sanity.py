"""Production sanity check：確認 production selector（gap=15、反手回測、最後選擇＝規則 B）與診斷結果一致。
用診斷時相同的條件（asof 2026-09-24、83 檔自身分佈當基準）；這只是確認實作與診斷一致，不是新的 ground truth。
1) SMCI→24、LMT→15、DIS→32、ACN→33、ROST→25（短期）  2) 全 83 檔短期 final ＝ 獨立以 final_rule_experiment.pick 計算的規則 B
3) 61 檔人工答案命中（資訊；規則 B 診斷值：±2 23/61、平均距離 4.656）
用法：python scripts/production_sanity.py [--asof 2026-09-24] [--out experiments/production_sanity] [--synthetic] [--only A,B]"""
import argparse, os, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
import regression as R, final_rule_experiment as fr
from core import data, score, select as sel
from core.universe import TICKERS

EXPECT = {'SMCI': 24, 'LMT': 15, 'DIS': 32, 'ACN': 33, 'ROST': 25}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='experiments/production_sanity'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='pswork_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True); os.chdir(wd)
    with ProcessPoolExecutor(4) as ex: newM = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in newM.items()], ignore_index=True); dfs = {tk: data.normalize(pd.read_csv(f'data_v/{tk}.csv'), a.asof) for tk in tks}
    prod, rows, bad = {}, [], []
    for tk in tks:
        Sx = score.score_table(newM[tk], ref); P_, Ss = sel.smoothed_scores(Sx); smo = dict(zip(P_, Ss))
        prod[tk] = sel.select(dfs[tk], Sx)                                                     # production 預設（gap=sel.GAP、反手、規則 B）
        old = sel.select(dfs[tk], Sx, final_rule='min_period')['短期']                          # 同一批候選，只為取得候選清單
        c = [dict(period=x['均線'], s=float(smo[x['均線']]), r=x['反手報酬']) for x in prod[tk]['短期']['cands']]
        indep = fr.pick('B_STRUCTURAL_TIEBREAK', c)
        if indep != prod[tk]['短期']['final'] or [x['均線'] for x in old['cands']] != [x['均線'] for x in prod[tk]['短期']['cands']]: bad.append(tk)
        rows.append(dict(ticker=tk, **{f'{nm}_final': prod[tk][nm]['final'] for nm in ('短期', '中期', '長期')}, short_candidates=' '.join(str(x['均線']) for x in prod[tk]['短期']['cands']), short_independent_ruleB=indep, min_period_rule_final=old['final']))
    T = pd.DataFrame(rows); T.to_csv(out / 'production_finals.csv', index=False)
    L = []; P = lambda *x: L.append(' '.join(str(i) for i in x))
    P(f'# Production sanity check（gap={sel.GAP}，asof {a.asof}，{len(tks)} 檔；基準＝這批股票自己）\n')
    P('| 股票 | 預期（診斷規則 B） | production 短期 final | 結果 |\n|---|---|---|---|'); allok = True
    for tk, e in EXPECT.items():
        if tk not in prod: P(f'| {tk} | {e} | 無資料 | 略過 |'); continue
        g = prod[tk]['短期']['final']; ok = g == e; allok &= ok; P(f'| {tk} | {e} | {g} | {"PASS" if ok else "FAIL"} |')
    P(f'\n全部預期檔通過：{"是" if allok else "**否**"}')
    P(f'\n全 {len(tks)} 檔短期：production final 與獨立計算的規則 B 相同、且候選與舊規則相同：{"是" if not bad else "**否 → implementation bug：" + str(bad) + "**"}')
    user = {tk: [p for p in ps if p <= 33] for tk, ps in R.USER.items()}; gt = [tk for tk in tks if user.get(tk)]
    if gt:
        d = np.array([min(abs(prod[tk]['短期']['final'] - u) for u in user[tk]) for tk in gt])
        P(f'\n61 檔人工答案（資訊）：final exact {int((d == 0).sum())}／±1 {int((d <= 1).sum())}／±2 {int((d <= 2).sum())}／±3 {int((d <= 3).sum())}（分母 {len(gt)}）；平均距離 {d.mean():.3f}，中位數 {np.median(d)}。診斷（規則 B）：±2 23/61、平均 4.656。')
    if fails: P('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails))
    (out / 'sanity_report.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
