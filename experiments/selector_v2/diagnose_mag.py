"""突破幅度實驗（MAGNITUDE_SPEC.md）的 83 檔診斷（開發集、資訊用，不是驗證）：同 diagnose_v2 的條件（asof 2026-09-24、基準＝這批股票自己）
四個版本並列：現行（select.select＋score_table）、現行＋幅度（select.select＋score_table_mag，基準＝自建 ref_mag）、v2（select_v2）、v2＋幅度（select_v2＋score_table_v2_mag）
輸出 diag_mag/diag_report.md＋finals.csv（不覆蓋 diag/）：15–45 人工線命中／涵蓋、46–70、擠向區間長端、第二條來源、逐檔、幅度特徵與週期的關係
用法：python experiments/selector_v2/diagnose_mag.py [--asof 2026-09-24] [--out experiments/selector_v2/diag_mag] [--synthetic] [--only A,B] [--w-mag 0.2]"""
import argparse, os, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts'), str(Path(__file__).resolve().parent)]
import regression as R
import build_reference_mag as brm
from diagnose_v2 import near, cover, TOLD
from core import data, score, select as sel, score_v2, score_mag
from core.select_v2 import select_v2, SHORT, MID
from core.universe import TICKERS
VERS = ('cur', 'curm', 'v2', 'v2m')                           # 現行、現行＋幅度、v2、v2＋幅度
NAMES = {'cur': '現行', 'curm': '現行＋幅度', 'v2': 'v2', 'v2m': 'v2＋幅度'}

def run_one(a):
    tk, asof, ref, ref2, refm, w_mag = a
    df = data.normalize(pd.read_csv(f'data_v/{tk}.csv'), asof); M = M_ALL[tk]
    P = sel.select(df, score.score_table(M, ref)); Pm = sel.select(df, score_mag.score_table_mag(M, refm, w_mag=w_mag))
    V = select_v2(df, M, ref2, long_result=P['長期']); Vm = select_v2(df, M, refm, long_result=Pm['長期'], score_fn=partial(score_mag.score_table_v2_mag, w_mag=w_mag))
    return tk, P, Pm, V, Vm

def main():
    global M_ALL
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='experiments/selector_v2/diag_mag'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); ap.add_argument('--w-mag', type=float, default=score_mag.W_MAG); a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='magdiag_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True); os.chdir(wd)
    with ProcessPoolExecutor(4) as ex: M_ALL = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in M_ALL.items()], ignore_index=True)
    ref2 = pd.concat([score_v2.make_features_v2(M).assign(ticker=tk) for tk, M in M_ALL.items()], ignore_index=True)
    refm = pd.concat([brm.features(M).assign(ticker=tk) for tk, M in M_ALL.items()], ignore_index=True)
    with ProcessPoolExecutor(4) as ex: res = {tk: r for tk, *r in ex.map(run_one, [(tk, a.asof, ref, ref2, refm, a.w_mag) for tk in tks])}
    rows = []
    for tk in tks:
        P, Pm, V, Vm = res[tk]; u = R.USER.get(tk, []); us = [p for p in u if SHORT[0] <= p <= SHORT[1]]; um = [p for p in u if MID[0] <= p <= MID[1]]
        r = dict(ticker=tk, user=' '.join(map(str, u)), user_15_45=' '.join(map(str, us)), user_46_70=' '.join(map(str, um)), n_us=len(us))
        for v, X in (('cur', P), ('curm', Pm)):
            s, m, l = X['短期']['final'], X['中期']['final'], X['長期']['final']
            r.update({f'{v}_short': s, f'{v}_mid': m, f'{v}_long': l, f'{v}_short_cands': ' '.join(f"{c['均線']}({c['分數']})" for c in X['短期']['cands']),
                      f'd_{v}_single': near(s, us), f'd_{v}_pair': near(s, us) if not us else min(near(s, us), near(m, us)), f'cov_{v}': cover([s, m], us)[0], f'd_{v}_long': near(l, um)})
        for v, X in (('v2', V), ('v2m', Vm)):
            s = X['短期']; f1, f2, vm = s['final1'], s['final2'], X['中期']['final']
            r.update({f'{v}_final1': f1, f'{v}_final2': f2, f'{v}_second_source': s['second_source'], f'{v}_mid': vm,
                      f'{v}_short_cands': ' '.join(f"{c['均線']}({c['分數_2y']})" for c in s['cands']), f'{v}_mid_cands': ' '.join(f"{c['均線']}({c['分數_3y']})" for c in X['中期']['cands']),
                      f'd_{v}_single': near(f1, us), f'd_{v}_pair': min(near(f1, us), near(f2, us)) if f2 is not None else near(f1, us), f'cov_{v}': cover([f1, f2], us)[0], f'd_{v}_mid': near(vm, um)})
        rows.append(r)
    T = pd.DataFrame(rows); T.to_csv(out / 'finals.csv', index=False)
    L = []; Pr = lambda *x: L.append(' '.join(str(i) for i in x))
    def hit(col, sub): d = sub[col].dropna(); return f"{int((d <= TOLD).sum())}/{len(d)}", f"{d.mean():.2f}" if len(d) else '—', f"{d.median():.1f}" if len(d) else '—'
    Pr(f'# 突破幅度實驗診斷（開發集 {len(tks)} 檔，asof {a.asof}，基準＝這批股票自己，幅度權重 {a.w_mag:.2f}{"，合成資料" if a.synthetic else ""}）\n')
    Pr('四個版本：現行／現行＋幅度（select.select 搭 score_table_mag）／v2／v2＋幅度（select_v2 搭 score_table_v2_mag）。人工標記也被用來開發現行規則，所以這裡只是診斷，不是驗證。命中＝距離 ≤2。\n')
    sub = T[T.n_us > 0]; tot = int(sub.n_us.sum())
    Pr(f'## 1. 15–45 的人工線（{len(sub)} 檔、共 {tot} 條）\n')
    Pr('| 版本 | 單條 final 命中（±2） | 平均距離 | 中位數 | 兩條（取較近）命中 | 平均距離 | 中位數 | 人工線涵蓋 |\n|---|---|---|---|---|---|---|---|')
    sn = {'cur': '短期 final（15–33）', 'curm': '短期 final（15–33）', 'v2': 'final1（15–45）', 'v2m': 'final1（15–45）'}; pn = {'cur': '短期＋中期 final', 'curm': '短期＋中期 final', 'v2': 'final1＋final2', 'v2m': 'final1＋final2'}
    for v in VERS: Pr(f'| {NAMES[v]}（單：{sn[v]}；兩條：{pn[v]}） | ' + ' | '.join(hit(f'd_{v}_single', sub) + hit(f'd_{v}_pair', sub)) + f' | {int(sub[f"cov_{v}"].sum())}/{tot} |')
    m2 = sub[sub.n_us >= 2]; Pr(f"\n有 ≥2 條人工線（15–45）的 {len(m2)} 檔：兩條都涵蓋 " + '、'.join(f"{NAMES[v]} {int((m2[f'cov_{v}'] >= 2).sum())}" for v in VERS))
    for x, y in (('curm', 'cur'), ('v2m', 'v2')):
        b = (sub[f'd_{x}_pair'] < sub[f'd_{y}_pair']).sum(); w = (sub[f'd_{x}_pair'] > sub[f'd_{y}_pair']).sum(); Pr(f'逐檔（兩條取較近）：{NAMES[x]} 較近 {b}、相同 {len(sub) - b - w}、{NAMES[y]} 較近 {w}')
    subm = T[T.user_46_70 != '']
    Pr(f'\n## 2. 46–70 的人工線（{len(subm)} 檔）\n\n| 比較 | 命中（±2） | 平均距離 | 中位數 |\n|---|---|---|---|')
    for nm, col in (('現行 長期 final（46–110，近 3 年）', 'd_cur_long'), ('現行＋幅度 長期 final（46–110）', 'd_curm_long'), ('v2 中期 final（46–70，近 3 年）', 'd_v2_mid'), ('v2＋幅度 中期 final（46–70，近 3 年）', 'd_v2m_mid')): Pr(f'| {nm} | ' + ' | '.join(hit(col, subm)) + ' |')
    Pr('\n## 3. 是否擠向區間長端（所有 final）\n\n| 線 | 區間 | 落在最後 3 個週期 | 落在最前 3 個週期 | 中位數 | 分佈（四分位） |\n|---|---|---|---|---|---|')
    for nm, col, lo, hi in (('現行 短期', 'cur_short', 15, 33), ('現行＋幅度 短期', 'curm_short', 15, 33), ('現行 中期', 'cur_mid', 34, 45), ('現行＋幅度 中期', 'curm_mid', 34, 45),
                            ('v2 final1', 'v2_final1', *SHORT), ('v2＋幅度 final1', 'v2m_final1', *SHORT), ('v2 final2', 'v2_final2', *SHORT), ('v2＋幅度 final2', 'v2m_final2', *SHORT),
                            ('v2 中期', 'v2_mid', *MID), ('v2＋幅度 中期', 'v2m_mid', *MID), ('現行 長期', 'cur_long', 46, 110), ('現行＋幅度 長期', 'curm_long', 46, 110)):
        x = T[col].dropna().astype(int)
        Pr(f'| {nm} | {lo}–{hi} | {int((x >= hi - 2).sum())}/{len(x)} | {int((x <= lo + 2).sum())}/{len(x)} | {x.median():.0f} | {" / ".join(f"{q:.0f}" for q in x.quantile([.25, .5, .75]))} |')
    Pr('\n## 4. v2 第二條來源與加幅度後的變化\n')
    for v in ('v2', 'v2m'): Pr(f"- {NAMES[v]} 第二條來源：候選 {int((T[f'{v}_second_source'] == 'cands').sum())}、放寬 {int((T[f'{v}_second_source'] == 'relaxed').sum())}、找不到 {int(T[f'{v}_second_source'].isna().sum())}（共 {len(T)}）")
    for x, y, cs in (('curm', 'cur', ('short', 'mid', 'long')), ('v2m', 'v2', ('final1', 'final2', 'mid'))):
        Pr(f"- {NAMES[x]} 相對 {NAMES[y]}：" + '、'.join(f"{c} 不變 {int(((T[f'{x}_{c}'] == T[f'{y}_{c}']) | (T[f'{x}_{c}'].isna() & T[f'{y}_{c}'].isna())).sum())}/{len(T)}" for c in cs))
    Pr('\n## 5. 幅度特徵與週期的關係（基準＝這批股票自己，各週期 SMA 的幅度平均；單位＝ATR）\n\n| 週期 | 幅度_1y | 幅度_2y | 幅度_3y |\n|---|---|---|---|')
    G = refm.groupby('period')[['幅度_1y', '幅度_2y', '幅度_3y']].mean()
    for p in range(15, 111, 5): Pr(f'| {p} | ' + ' | '.join(f'{G.loc[p, c]:.3f}' for c in G.columns) + ' |')
    Pr('\n週期與幅度的 Spearman 相關（基準全部列）：' + '、'.join(f"{c} {refm['period'].rank().corr(refm[c].rank()):.3f}" for c in G.columns))
    Pr('\n## 6. 逐檔（有 15–45 或 46–70 人工線者；短／中／長 或 f1／f2／中）\n\n| 股票 | 人工 | 現行 短／中／長 | 現行＋幅度 短／中／長 | v2 f1／f2／中 | v2＋幅度 f1／f2／中 |\n|---|---|---|---|---|---|')
    f2s = lambda r, v: '—' if pd.isna(getattr(r, f'{v}_final2')) else f"{int(getattr(r, f'{v}_final2'))}" + ('ʳ' if getattr(r, f'{v}_second_source') == 'relaxed' else '')
    for r in T[(T.n_us > 0) | (T.user_46_70 != '')].itertuples():
        Pr(f'| {r.ticker} | {r.user} | {r.cur_short}／{r.cur_mid}／{r.cur_long} | {r.curm_short}／{r.curm_mid}／{r.curm_long} | {r.v2_final1}／{f2s(r, "v2")}／{r.v2_mid} | {r.v2m_final1}／{f2s(r, "v2m")}／{r.v2m_mid} |')
    Pr('\nʳ＝第二條來自放寬候選。')
    if fails: Pr('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails))
    (out / 'diag_report.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L))

M_ALL = {}
if __name__ == '__main__': main()
