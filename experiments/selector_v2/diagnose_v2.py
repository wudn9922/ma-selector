"""selector v2 的 83 檔診斷（開發集、資訊用，不是驗證）：同 production_sanity 的條件（asof 2026-09-24、基準＝這批股票自己）
比較現行 select() 與 select_v2() 對 70 檔人工標記（scripts/regression.USER）的距離；人工標記同時也是開發現行規則時用過的資料，所以只算診斷。
1) 15–45 的人工線：現行（短期 final＋中期 final 兩條）vs v2（短期 final1＋final2）各涵蓋幾條（±2）；單條 final 的最近距離
2) 46–70 的人工線：v2 中期 final vs 現行長期 final
3) 擠向區間長端：final 落在區間最後 3 個週期的比例、final 分佈
用法：python experiments/selector_v2/diagnose_v2.py [--asof 2026-09-24] [--out experiments/selector_v2/diag] [--synthetic] [--only A,B]"""
import argparse, os, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
import regression as R
from core import data, score, select as sel, score_v2
from core.select_v2 import select_v2, SHORT, MID
from core.universe import TICKERS
TOLD = 2                                          # 命中＝距離 ≤2

def run_one(a):
    tk, asof, ref, ref2 = a
    df = data.normalize(pd.read_csv(f'data_v/{tk}.csv'), asof); M = M_ALL[tk]
    S = score.score_table(M, ref); P = sel.select(df, S); V = select_v2(df, M, ref2, long_result=P['長期'])
    return tk, P, V

def near(x, labels): return min(abs(x - u) for u in labels) if (x is not None and labels) else np.nan

def cover(lines, labels):
    """每條人工線是否有某條選出的線在 ±2 內 → (涵蓋數, 人工線數)"""
    ls = [x for x in lines if x is not None]; return sum(any(abs(x - u) <= TOLD for x in ls) for u in labels), len(labels)

def main():
    global M_ALL
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='experiments/selector_v2/diag'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='v2diag_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True); os.chdir(wd)
    with ProcessPoolExecutor(4) as ex: M_ALL = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in M_ALL.items()], ignore_index=True)
    ref2 = pd.concat([score_v2.make_features_v2(M).assign(ticker=tk) for tk, M in M_ALL.items()], ignore_index=True)
    with ProcessPoolExecutor(4) as ex: res = {tk: (P, V) for tk, P, V in ex.map(run_one, [(tk, a.asof, ref, ref2) for tk in tks])}
    rows = []
    for tk in tks:
        P, V = res[tk]; u = R.USER.get(tk, []); us = [p for p in u if SHORT[0] <= p <= SHORT[1]]; um = [p for p in u if MID[0] <= p <= MID[1]]; s = V['短期']
        cs, cm, cl = P['短期']['final'], P['中期']['final'], P['長期']['final']; f1, f2, vm = s['final1'], s['final2'], V['中期']['final']
        rows.append(dict(ticker=tk, user=' '.join(map(str, u)), user_15_45=' '.join(map(str, us)), user_46_70=' '.join(map(str, um)),
                         cur_short=cs, cur_mid=cm, cur_long=cl, v2_final1=f1, v2_final2=f2, v2_second_source=s['second_source'], v2_mid=vm,
                         v2_short_cands=' '.join(f"{c['均線']}({c['分數_2y']})" for c in s['cands']), v2_relaxed=' '.join(str(c['均線']) for c in s['relaxed']),
                         v2_mid_cands=' '.join(f"{c['均線']}({c['分數_3y']})" for c in V['中期']['cands']),
                         cur_short_cands=' '.join(f"{c['均線']}({c['分數']})" for c in P['短期']['cands']),
                         suit_short_2y=round(V['suitability']['short_2y'], 2), suit_short_1y=round(V['suitability']['short_1y'], 2), suit_mid_3y=round(V['suitability']['mid_3y'], 2),
                         d_cur_short=near(cs, us), d_cur_pair=near(cs, us) if not us else min(near(cs, us), near(cm, us)), d_v2_f1=near(f1, us),
                         d_v2_pair=min(near(f1, us), near(f2, us)) if f2 is not None else near(f1, us),
                         cov_cur=cover([cs, cm], us)[0], cov_v2=cover([f1, f2], us)[0], n_us=len(us), d_v2_mid=near(vm, um), d_cur_long=near(cl, um)))
    T = pd.DataFrame(rows); T.to_csv(out / 'v2_finals.csv', index=False)
    L = []; Pr = lambda *x: L.append(' '.join(str(i) for i in x))
    def hit(col, sub): d = sub[col].dropna(); return f"{int((d <= TOLD).sum())}/{len(d)}", f"{d.mean():.2f}" if len(d) else '—', f"{d.median():.1f}" if len(d) else '—'
    Pr(f'# selector v2 診斷（開發集 {len(tks)} 檔，asof {a.asof}，基準＝這批股票自己{"，合成資料" if a.synthetic else ""}）\n')
    Pr('人工標記也被用來開發現行規則，所以這裡只是診斷，不是驗證。命中＝距離 ≤2。\n')
    sub = T[T.n_us > 0]
    Pr(f'## 1. 15–45 的人工線（{len(sub)} 檔、共 {int(sub.n_us.sum())} 條）\n')
    Pr('| 比較 | 命中（±2） | 平均距離 | 中位數 |\n|---|---|---|---|')
    for nm, col in (('現行 短期 final（15–33）', 'd_cur_short'), ('現行 兩條（短期＋中期 34–45）取較近', 'd_cur_pair'), ('v2 final1（15–45，近 2 年）', 'd_v2_f1'), ('v2 兩條（final1＋final2）取較近', 'd_v2_pair')):
        Pr(f'| {nm} | ' + ' | '.join(hit(col, sub)) + ' |')
    Pr(f"\n人工線涵蓋（每條人工線是否有選出的線在 ±2 內）：現行兩條 {int(sub.cov_cur.sum())}/{int(sub.n_us.sum())}；v2 兩條 {int(sub.cov_v2.sum())}/{int(sub.n_us.sum())}")
    m2 = sub[sub.n_us >= 2]; Pr(f"有 ≥2 條人工線（15–45）的 {len(m2)} 檔：兩條都涵蓋 現行 {int((m2.cov_cur >= 2).sum())}、v2 {int((m2.cov_v2 >= 2).sum())}")
    b = (sub.d_v2_pair < sub.d_cur_pair).sum(); w = (sub.d_v2_pair > sub.d_cur_pair).sum(); Pr(f'逐檔（兩條取較近）：v2 較近 {b}、相同 {len(sub) - b - w}、現行較近 {w}')
    subm = T[T.user_46_70 != '']
    Pr(f'\n## 2. 46–70 的人工線（{len(subm)} 檔）\n\n| 比較 | 命中（±2） | 平均距離 | 中位數 |\n|---|---|---|---|')
    for nm, col in (('現行 長期 final（46–110，近 3 年）', 'd_cur_long'), ('v2 中期 final（46–70，近 3 年）', 'd_v2_mid')): Pr(f'| {nm} | ' + ' | '.join(hit(col, subm)) + ' |')
    Pr('\n## 3. 是否擠向區間長端\n\n| 線 | 區間 | 落在最後 3 個週期 | 落在最前 3 個週期 | 中位數 | 分佈（四分位） |\n|---|---|---|---|---|---|')
    for nm, col, lo, hi in (('現行 短期', 'cur_short', 15, 33), ('v2 final1', 'v2_final1', *SHORT), ('v2 final2', 'v2_final2', *SHORT), ('v2 中期', 'v2_mid', *MID), ('現行 長期', 'cur_long', 46, 110)):
        x = T[col].dropna().astype(int)
        Pr(f'| {nm} | {lo}–{hi} | {int((x >= hi - 2).sum())}/{len(x)} | {int((x <= lo + 2).sum())}/{len(x)} | {x.median():.0f} | {" / ".join(f"{q:.0f}" for q in x.quantile([.25, .5, .75]))} |')
    Pr(f"\nv2 第二條來源：候選 {int((T.v2_second_source == 'cands').sum())}、放寬 {int((T.v2_second_source == 'relaxed').sum())}、找不到 {int(T.v2_second_source.isna().sum())}（共 {len(T)}）")
    Pr(f"v2 final1 ≤33（舊短期範圍內）：{int((T.v2_final1 <= 33).sum())}/{len(T)}；v2 final1 與現行短期 final 相同：{int((T.v2_final1 == T.cur_short).sum())}/{len(T)}")
    Pr('\n## 4. 逐檔（有 15–45 或 46–70 人工線者）\n\n| 股票 | 人工 | 現行 短／中／長 | v2 短 f1／f2 | v2 中 | v2 短期候選（2y 分數） |\n|---|---|---|---|---|---|')
    for r in T[(T.n_us > 0) | (T.user_46_70 != '')].itertuples():
        f2 = '—' if pd.isna(r.v2_final2) else f'{int(r.v2_final2)}' + ('ʳ' if r.v2_second_source == 'relaxed' else '')
        Pr(f'| {r.ticker} | {r.user} | {r.cur_short}／{r.cur_mid}／{r.cur_long} | {r.v2_final1}／{f2} | {r.v2_mid} | {r.v2_short_cands} |')
    Pr('\nʳ＝第二條來自放寬候選。')
    if fails: Pr('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails))
    (out / 'diag_report.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L))

M_ALL = {}
if __name__ == '__main__': main()
