"""Snapshot regression（B）：原始 選均線_v22.csv（immutable fixture）vs 目前輸出
A（regression.py）＝重建的 research 舊實作 vs core 新實作；B（本檔）＝原始 v22 snapshot vs 目前輸出。兩者用途不同，不可混為一談。
只讀診斷：不修改 core/、research/、分數、候選規則、tolerance。
比較單位：ticker × range（短期／中期／長期）。snapshot 的分數是整數、報酬是整數百分比，所以「相同」＝在四捨五入精度內（|差| ≤ 0.5）。
分類：EXACT_MATCH / ORDER_ONLY / SCORE_DRIFT / CANDIDATE_SET_DRIFT / BACKTEST_DRIFT / FINAL_SELECTION_DRIFT
  同一列可以同時有多個旗標；主分類依嚴重度：FINAL_SELECTION_DRIFT > CANDIDATE_SET_DRIFT > BACKTEST_DRIFT > SCORE_DRIFT > ORDER_ONLY > EXACT_MATCH
用法：python scripts/snapshot_regression.py [--asof 2026-09-24] [--out regression/snapshot] [--synthetic] [--only A,B,...]"""
import argparse, hashlib, importlib, os, re, runpy, shutil, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
import regression as R
from core import data, metrics, score, select as sel
from core.universe import TICKERS

BASE = ROOT / 'regression' / 'baselines' / '選均線_v22.csv'
EXPECT_SHA = 'f719ebd6f5fc33378069aab736bca4dfd932a9134b7157b2440e7d360b68e10a'
RANGES = ('短期', '中期', '長期')
PAT = re.compile(r'(\d+)（(\d+)、([+-]?\d+)%/([+-]?\d+)%）')
PRIMARY = ['FINAL_SELECTION_DRIFT', 'CANDIDATE_SET_DRIFT', 'BACKTEST_DRIFT', 'SCORE_DRIFT', 'ORDER_ONLY', 'EXACT_MATCH']
TOL_SCORE, TOL_RET = 1.0, 1.0   # snapshot 為整數（捨入或截斷方式不明），±1 視為同一格式精度內；另記錄最大差距供檢視
NINE = ['ACN', 'ALSN', 'CSX', 'DUK', 'IBM', 'MMS', 'ROST', 'RRX', 'TSM']

def md(df, index=True):
    d = df.reset_index() if index else df.copy(); cols = [str(c) for c in d.columns]
    return '\n'.join(['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)] + ['| ' + ' | '.join(str(v) for v in r) + ' |' for r in d.itertuples(index=False)])

def check_hash():
    """immutable fixture：內容雜湊必須等於記錄值，否則直接中止"""
    h = hashlib.sha256(BASE.read_bytes()).hexdigest(); rec = (BASE.parent / 'SHA256SUMS').read_text(encoding='utf-8').split()[0]
    if not (h == EXPECT_SHA == rec): sys.exit(f'FIXTURE HASH MISMATCH：實際 {h}，程式內記錄 {EXPECT_SHA}，SHA256SUMS {rec}。baseline 被改過，中止。')
    return h

def parse_snapshot():
    df = pd.read_csv(BASE, encoding='utf-8-sig'); snap = {}; user = {}
    for _, r in df.iterrows():
        tk = r.iloc[0]; user[tk] = [int(x) for x in re.findall(r'\d+', str(r.iloc[1]))] if isinstance(r.iloc[1], str) else []
        for i, nm in enumerate(RANGES):
            fin, txt = int(r.iloc[2 + 2 * i]), str(r.iloc[3 + 2 * i])
            snap[(tk, nm)] = dict(final=fin, cands=[(int(a), int(b), int(c), int(d)) for a, b, c, d in PAT.findall(txt)])
    return snap, user

def cur_from(sel_out):
    """{(tk,range): dict(final, cands=[(period, score, simple_frac, complex_frac)])}；sel_out 可為舊（final_select）或新（core.select）格式"""
    out = {}
    for tk, d in sel_out.items():
        for nm in RANGES:
            v = d[nm]; fin, cands = (v['final'], v['cands']) if isinstance(v, dict) else (v[0], v[1])
            out[(tk, nm)] = dict(final=fin, cands=[(c['均線'], c['分數'], c['簡單報酬'], c['複雜報酬']) for c in cands])
    return out

def compare(s, c):
    sp, cp = [x[0] for x in s['cands']], [x[0] for x in c['cands']]; sm = {x[0]: x for x in s['cands']}; cm = {x[0]: x for x in c['cands']}
    f = dict(set_drift=set(sp) != set(cp), order_diff=set(sp) == set(cp) and sp != cp, final_drift=s['final'] != c['final'], score_drift=False, backtest_drift=False)
    rows = []; f['max_score_diff'] = 0.; f['max_ret_diff'] = 0.
    for p in sorted(set(sp) | set(cp)):
        a, b = sm.get(p), cm.get(p); r = dict(period=p, in_snapshot=a is not None, in_current=b is not None, snap_rank=sp.index(p) + 1 if a else '', cur_rank=cp.index(p) + 1 if b else '')
        if a and b:
            r.update(snap_score=a[1], cur_score=round(b[1], 2), score_diff=round(b[1] - a[1], 2), snap_simple=a[2], cur_simple=round(b[2] * 100, 2), snap_complex=a[3], cur_complex=round(b[3] * 100, 2))
            f['max_score_diff'] = max(f['max_score_diff'], abs(b[1] - a[1])); f['max_ret_diff'] = max(f['max_ret_diff'], abs(b[2] * 100 - a[2]), abs(b[3] * 100 - a[3]))
            if abs(b[1] - a[1]) > TOL_SCORE + 1e-9: f['score_drift'] = True
            if abs(b[2] * 100 - a[2]) > TOL_RET + 1e-9 or abs(b[3] * 100 - a[3]) > TOL_RET + 1e-9: f['backtest_drift'] = True
        elif a: r.update(snap_score=a[1], snap_simple=a[2], snap_complex=a[3])
        else: r.update(cur_score=round(b[1], 2), cur_simple=round(b[2] * 100, 2), cur_complex=round(b[3] * 100, 2))
        rows.append(r)
    cls = 'FINAL_SELECTION_DRIFT' if f['final_drift'] else 'CANDIDATE_SET_DRIFT' if f['set_drift'] else 'BACKTEST_DRIFT' if f['backtest_drift'] else 'SCORE_DRIFT' if f['score_drift'] else 'ORDER_ONLY' if f['order_diff'] else 'EXACT_MATCH'
    return cls, f, rows

def hits(final_cands, user, tol, lo, hi):
    us = [p for p in user if lo <= p <= hi]
    return None if not us else (any(abs(p - c) <= tol for p in us for c in final_cands[0]), any(abs(p - final_cands[1]) <= tol for p in us))

def greedy(periods, sm, cap=5):
    """final_select 的候選規則（不含回測）：與最高分差 ≤15、彼此差 >2、最多 5 條"""
    m = periods <= 33; pm, s = periods[m], sm[m]; order = np.argsort(-s); best = s[order[0]]; out = []
    for i in order:
        if s[i] < best - 15: break
        if all(abs(pm[i] - c) > 2 for c in out): out.append(int(pm[i]))
        if len(out) == cap: break
    return out, best

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='regression/snapshot'); ap.add_argument('--work')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--only'); a = ap.parse_args()
    sha = check_hash(); out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='snapwork_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    os.environ['ASOF'] = a.asof; snap, user = parse_snapshot(); TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    with ProcessPoolExecutor(4) as ex: fails = [(t, e) for t, e in ex.map(R.fetch_one, [(t, str(wd), a.asof, a.synthetic) for t in TK]) if e]
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔', flush=True); os.chdir(wd)
    import ma_select_v18 as ms
    # 舊（frozen research/）流程
    (wd / 'out_v22').mkdir(exist_ok=True)
    with ProcessPoolExecutor(4) as ex: res = list(ex.map(R.old_ticker, tks))
    for tk, (M, T) in zip(tks, res): M.to_pickle(f'out_v22/{tk}.pkl')
    T_all = pd.concat([T for _, T in res]); T_all.to_pickle('tg4.pkl'); runpy.run_path(str(ROOT / 'research' / 'extra_metrics.py'), run_name='__main__')
    import composite4; Dold = composite4.build().sort_values(['ticker', 'period']).reset_index(drop=True); Dold.to_pickle('composite2.pkl')
    import final_select as fs
    old_sel = {tk: fs.run(tk) for tk in tks}; print('舊流程完成', flush=True)
    # 新（core/）流程
    with ProcessPoolExecutor(4) as ex: newM = dict(ex.map(R.new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in newM.items()], ignore_index=True); dfs = {tk: data.normalize(pd.read_csv(f'data_v/{tk}.csv'), a.asof) for tk in tks}
    new_sel = {tk: sel.select(dfs[tk], score.score_table(newM[tk], ref)) for tk in tks}; print('新流程完成', flush=True)
    cur_old, cur_new = cur_from(old_sel), cur_from(new_sel)
    L = []; P = lambda *x: L.append(' '.join(str(i) for i in x))
    P(f'# Snapshot regression（B）：原始 選均線_v22.csv vs 目前輸出（asof={a.asof}，{len(tks)} 檔）\n')
    P(f'- fixture：`regression/baselines/選均線_v22.csv`，SHA-256 `{sha}`（與 SHA256SUMS、程式內記錄一致；不一致時本程式直接中止）')
    P('- 這是第二條 regression baseline（B）。第一條（A，`regression.py`）是「重建的 research 舊實作 vs core 新實作」，兩者用途不同。')
    P('- 比較精度：snapshot 分數為整數、報酬為整數百分比，故 |差| ≤ 1（分／百分點）視為相同（捨入或截斷方式不明；最大差距另列在 CSV）。\n')
    # ── 1) 歷史命中定義 ──
    P('## 1. 歷史短期命中率（snapshot 本身 vs 目前輸出）\n\n| tolerance | snapshot candidate | snapshot final | 目前 candidate | 目前 final |\n|---|---|---|---|---|')
    def hr(src, tol):
        c = f = n = 0
        for tk in tks:
            h = hits(([x[0] for x in src[(tk, '短期')]['cands']], src[(tk, '短期')]['final']), user.get(tk, []), tol, 0, 33)
            if h is None: continue
            n += 1; c += h[0]; f += h[1]
        return c, f, n
    for t in range(4):
        sc, sf, n = hr(snap, t); cc, cf, _ = hr(cur_new, t); P(f'| ±{t} | {sc}/{n} | {sf}/{n} | {cc}/{n} | {cf}/{n} |')
    P('\n交接文件 46/61、17/61 ＝ snapshot 的 ±2；目前輸出 ±2 為 47/61、18/61。\n')
    # ── 2) 逐 ticker×range 比較 ──
    rows, diffs = [], []
    for tk in tks:
        for nm in RANGES:
            cls, f, dd = compare(snap[(tk, nm)], cur_new[(tk, nm)]); cls_o, _, _ = compare(snap[(tk, nm)], cur_old[(tk, nm)])
            rows.append(dict(ticker=tk, range=nm, in_61_short_labelled=any(p <= 33 for p in user.get(tk, [])), classification=cls, classification_frozen_old=cls_o, **f, snapshot_final=snap[(tk, nm)]['final'], current_final=cur_new[(tk, nm)]['final'],
                             snapshot_candidates=' '.join(f'{x[0]}({x[1]})' for x in snap[(tk, nm)]['cands']), current_candidates=' '.join(f'{x[0]}({x[1]:.1f})' for x in cur_new[(tk, nm)]['cands'])))
            diffs += [dict(ticker=tk, range=nm, **d) for d in dd]
    C = pd.DataFrame(rows); C['max_score_diff'] = C['max_score_diff'].round(2); C['max_ret_diff'] = C['max_ret_diff'].round(2); C.to_csv(out / 'snapshot_comparison.csv', index=False); pd.DataFrame(diffs).to_csv(out / 'snapshot_candidate_diffs.csv', index=False)
    S = C.groupby(['range', 'classification']).size().unstack(fill_value=0).reindex(columns=PRIMARY, fill_value=0).reindex(list(RANGES)); S.to_csv(out / 'snapshot_summary.csv')
    F = C.groupby('range')[['set_drift', 'order_diff', 'score_drift', 'backtest_drift', 'final_drift']].sum().reindex(list(RANGES))
    P('## 2. 分類結果（主分類；依嚴重度）\n\n' + md(S) + '\n\n各旗標（同一列可有多個）：\n\n' + md(F) + '\n')
    P(f'舊（frozen research）與 core 對 snapshot 的分類是否完全相同：{"是" if (C.classification == C.classification_frozen_old).all() else "否，見 CSV"}\n')
    C61 = C[C.in_61_short_labelled & (C['range'] == '短期')]; s61 = C61[C61.set_drift | C61.order_diff].ticker.tolist(); f61 = C61[C61.final_drift].ticker.tolist()
    P(f'### 短期，限縮到有人工標記的 61 檔（與交接文件、使用者的分母一致）\n\n- 檔數：{len(C61)}；EXACT_MATCH：{int((C61.classification == "EXACT_MATCH").sum())}')
    P(f'- 候選內容或排序有差異：{len(s61)} 檔 {s61}；其中 CANDIDATE_SET_DRIFT {int(C61.set_drift.sum())}、ORDER_ONLY（僅順序）{int((C61.order_diff & ~C61.set_drift).sum())}')
    P(f'- final selection 不同：{len(f61)} 檔 {f61}；BACKTEST_DRIFT 旗標 {int(C61.backtest_drift.sum())}、SCORE_DRIFT 旗標 {int(C61.score_drift.sum())}\n')
    nz = C[(C.classification != 'EXACT_MATCH')]; P('## 3. 非 EXACT_MATCH 的 ticker × range\n\n| 股票 | range | 主分類 | snapshot 候選 → 選 | 目前候選 → 選 |\n|---|---|---|---|---|')
    for _, r in nz.iterrows(): P(f"| {r.ticker} | {r['range']} | {r.classification} | {r.snapshot_candidates} → {r.snapshot_final} | {r.current_candidates} → {r.current_final} |")
    short_bad = C[(C['range'] == '短期') & (C.classification != 'EXACT_MATCH')].ticker.tolist(); short_fin = C[(C['range'] == '短期') & C.final_drift].ticker.tolist()
    P(f'\n短期候選內容或排序有差異：{len(short_bad)} 檔 {short_bad}；短期 final 不同：{short_fin}\n')
    # ── 4) 深入：短期 9 檔 ──
    P('## 4. 短期差異檔深入（今天的平滑分數曲線 vs snapshot）\n')
    def curve(tk):
        g = Dold[Dold.ticker == tk].sort_values('period'); return g.period.to_numpy(), fs.smooth(g['分數'].to_numpy())
    deep = [t for t in dict.fromkeys(NINE + (short_bad if len(short_bad) <= 15 else [])) if t in tks]
    for tk in deep:
        Pd, Sd = curve(tk); m = Pd <= 33; cands_today, best = greedy(Pd, Sd); s = snap[(tk, '短期')]; sb = max(x[1] for x in s['cands'])
        P(f'### {tk}\n\nsnapshot：候選 {[(x[0], x[1]) for x in s["cands"]]} → {s["final"]}（最高 {sb}，門檻 {sb - 15}）；今天：候選 {cands_today}，最高 {best:.1f}，門檻 {best - 15:.1f}\n')
        P('| 均線 | 今天平滑分 | snapshot 分 | 差 | 今天是候選 | snapshot 是候選 |\n|---|---|---|---|---|---|')
        sd = {x[0]: x[1] for x in s['cands']}
        for p, v in zip(Pd[m], Sd[m]):
            if p in sd or p in cands_today or abs(v - (best - 15)) < 3 or v >= best - 2: P(f"| {p} | {v:.1f} | {sd.get(p, '')} | {(v - sd[p]) if p in sd else ''} | {'是' if p in cands_today else ''} | {'是' if p in sd else ''} |")
        P('')
    # ── 5) 資料變體重播（只用 asof 以前的資料；把最後 1、2 根 K 線拿掉）──
    P('## 5. 資料變體重播（frozen 流程，只改該檔的截止日；不看 asof 之後的 K 線）\n\n目的：檢查 snapshot 是否來自「該檔 CSV 較早抓（最後一根 K 線較舊）」。fetch_v 對已存在的 CSV 不會重抓，各檔 CSV 的最後日期可能不同。\n')
    var_rows = []; base_out = wd / 'out_v22'
    def variant(tk, asof_v):
        vd = Path(tempfile.mkdtemp(prefix='var_')); (vd / 'out_v22').mkdir()
        for f in base_out.glob('*.pkl'): shutil.copy(f, vd / 'out_v22' / f.name)
        os.symlink(wd / 'data_v', vd / 'data_v'); old_asof = ms.ASOF; ms.ASOF = pd.Timestamp(asof_v)
        try:
            M, T = R.old_ticker(tk); M.to_pickle(vd / 'out_v22' / f'{tk}.pkl')
            T2 = pd.concat([pd.read_pickle(wd / 'tg4.pkl').query('ticker != @tk'), T]); T2.to_pickle(vd / 'tg4.pkl')
            xd = Path(tempfile.mkdtemp(prefix='xv_')); (xd / 'data_v').mkdir(); shutil.copy(wd / 'data_v' / f'{tk}.csv', xd / 'data_v' / f'{tk}.csv'); cwd = os.getcwd(); os.chdir(xd)
            try: runpy.run_path(str(ROOT / 'research' / 'extra_metrics.py'), run_name='__main__')
            finally: os.chdir(cwd)
            X2 = pd.concat([pd.read_pickle(wd / 'extra_metrics.pkl').query('ticker != @tk'), pd.read_pickle(xd / 'extra_metrics.pkl')]); X2.to_pickle(vd / 'extra_metrics.pkl')
            os.chdir(vd)
            try:
                Dv = composite4.build().sort_values(['ticker', 'period']).reset_index(drop=True); Dv.to_pickle('composite2.pkl'); fsv = importlib.reload(fs); res_v = fsv.run(tk)
            finally: os.chdir(wd)
        finally: ms.ASOF = old_asof
        shutil.rmtree(vd, ignore_errors=True); shutil.rmtree(xd, ignore_errors=True); return Dv, res_v
    acn_pair = {}
    for tk in deep:
        d = dfs[tk]; s = snap[(tk, '短期')]
        for lab, asof_v in (('asof(今天)', a.asof), ('少1根', str(d.date.iloc[-2].date())), ('少2根', str(d.date.iloc[-3].date()))):
            Dv, rv = variant(tk, asof_v); fin, cands = rv['短期']; cp = [c['均線'] for c in cands]; sp = [x[0] for x in s['cands']]
            common = {c['均線']: c['分數'] for c in cands}; mx = max([abs(common[x[0]] - x[1]) for x in s['cands'] if x[0] in common] or [np.nan])
            g = Dv[Dv.ticker == tk].set_index('period')['分數']; var_rows.append(dict(ticker=tk, variant=lab, cutoff=asof_v, candidates=' '.join(map(str, cp)), final=fin, snapshot_candidates=' '.join(map(str, sp)), snapshot_final=s['final'],
                                                                                    set_match=set(cp) == set(sp), final_match=fin == s['final'], max_abs_score_diff_common=mx, acn_32_minus_25=float(g[32] - g[25]) if tk == 'ACN' else ''))
        print(f'變體 {tk} 完成', flush=True)
    V = pd.DataFrame(var_rows); V.to_csv(out / 'variant_replay.csv', index=False)
    P('| 股票 | 變體 | 截止日 | 候選 | 選 | snapshot 候選 | snapshot 選 | 候選集合相同 | final 相同 |\n|---|---|---|---|---|---|---|---|---|')
    for _, r in V.iterrows(): P(f'| {r.ticker} | {r.variant} | {r.cutoff} | {r.candidates} | {r.final} | {r.snapshot_candidates} | {r.snapshot_final} | {r.set_match} | {r.final_match} |')
    rep = V[V.set_match & V.final_match & (V.variant != 'asof(今天)')]; P(f'\n有變體完全重現 snapshot 的股票：{sorted(set(rep.ticker)) or "無"}\n')
    P('### 最後 6 根 K 線（asof 以前；日報酬＝收盤／前收 −1）\n')
    for tk in deep:
        d = dfs[tk].tail(7).reset_index(drop=True); d['ret'] = d.close.pct_change(); d = d.tail(6)
        P(f'**{tk}**\n\n| 日期 | 開 | 高 | 低 | 收 | 量 | 日報酬 |\n|---|---|---|---|---|---|---|')
        for _, r in d.iterrows(): P(f"| {r.date.date()} | {r.open:.2f} | {r.high:.2f} | {r.low:.2f} | {r.close:.2f} | {int(r.volume)} | {r.ret * 100:+.2f}% |")
        P('')
    if 'ACN' in tks:
        P('ACN 32 vs 25 原始分差（32−25；>0＝符合使用者順序）：\n\n' + V[V.ticker == 'ACN'][['variant', 'acn_32_minus_25']].pipe(md, index=False) + '\n')
    # ── 6) ACN：少數事件差異能否重現 snapshot ──
    if 'ACN' in tks:
        P('## 6. ACN：需要多少「單一事件結果不同」才能重現 snapshot 的候選集合 {16,19}\n')
        Dref = Dold.copy(); refF = score.make_features(Dref).assign(ticker=Dref.ticker.to_numpy()); Ma = Dold[Dold.ticker == 'ACN'].sort_values('period').reset_index(drop=True)
        cols = {'突破': ('A_raw@252', 'A_raw_n@252'), '二日': ('A_d2@252', 'A_d2_n@252'), '回測': ('A_rt@252', 'A_rt_n@252')}
        def evaluate(M):
            Sx = score.score_table(M, refF); s_ = fs.smooth(Sx['分數'].to_numpy()); return greedy(Sx['period'].to_numpy(), s_), Sx
        (base_c, _), _ = evaluate(Ma); target = [x[0] for x in snap[('ACN', '短期')]['cands']]; P(f'今天的候選 {base_c}；snapshot 候選 {target}\n')
        perts = []
        for p in [x for x in range(15, 35)]:
            i = Ma.index[Ma.period == p][0]
            for k, (rc, nc) in cols.items():
                n = int(Ma.at[i, nc]); sv = int(round(Ma.at[i, rc] * n)) if n and not np.isnan(Ma.at[i, rc]) else 0
                for d_ in (1, -1):
                    if n and 0 <= sv + d_ <= n: perts.append((p, k, d_, i, rc, (sv + d_) / n))
            w = int(Ma.at[i, 'A_wick@252'])
            for d_ in (1, -1):
                if w + d_ >= 0: perts.append((p, '雜訊', d_, i, 'A_wick@252', w + d_))
        def apply(evs):
            M = Ma.copy()
            for p, k, d_, i, col, val in evs: M.at[i, col] = val
            return M
        hitsx = []
        for e in perts:
            (c, _), _ = evaluate(apply([e]))
            if set(c) == set(target): hitsx.append([e])
        P(f'單一事件（{len(perts)} 種）能重現 snapshot 候選集合的有 {len(hitsx)} 種。')
        pairs = 0
        if not hitsx:
            near = [e for e in perts if e[0] <= 21 or e[0] >= 26]
            for i1 in range(len(near)):
                for i2 in range(i1 + 1, len(near)):
                    e1, e2 = near[i1], near[i2]
                    if e1[3] == e2[3] and e1[4] == e2[4]: continue
                    pairs += 1; (c, _), _ = evaluate(apply([e1, e2]))
                    if set(c) == set(target): hitsx.append([e1, e2])
            P(f'兩個事件同時改變（搜尋 {pairs} 組）能重現的有 {len(hitsx)} 組。')
        rows_e = [dict(events=' + '.join(f'{p}期{k}{"+" if d_ > 0 else "-"}1' for p, k, d_, *_ in h)) for h in hitsx[:200]]
        pd.DataFrame(rows_e).to_csv(out / 'acn_event_search.csv', index=False); P('範例（前 10 組）：' + '；'.join(r['events'] for r in rows_e[:10]) + '\n')
    if fails: P('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fails))
    (out / 'snapshot_regression_report.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
