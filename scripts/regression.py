"""Frozen / authoritative regression：舊實作（research/ 原檔）vs 新實作（core/）逐層比較
舊：research/metrics_v22.py（交接 7-2 重建）→ research/extra_metrics.py → research/composite4.py → research/final_select.py（皆原檔，不改）
新：core.metrics → core.score → core.select
兩邊讀同一批 CSV（同一份 Yahoo 資料、asof 固定 2026-09-24），基準＝這 83 檔自己（同 composite4）。
用法：python scripts/regression.py [--asof 2026-09-24] [--out regression] [--synthetic] [--inject-bug]
分類：MATCH / NUMERICAL_TOLERANCE / DATA_DIFFERENCE / IMPLEMENTATION_BUG / RULE_CONFLICT / NEEDS_HUMAN_REVIEW
不做任何「比研究版高就 PASS」的判定；圖與 LMT／ACN／DIS 一律 NEEDS_HUMAN_REVIEW，除非 regression/human_review.json 有人工確認（PASS＝方向成立；TIE＝近似平手，不解讀為方向）。"""
import argparse, hashlib, json, os, re, runpy, subprocess, sys, tempfile, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'research'), str(ROOT / 'scripts')]
from core import data, metrics, score, select as sel, charts
from core.universe import TICKERS

USER_TXT = """AAPL[24,58] ABT[35,38] ACN[25,27,32,46] ADBE[20,63] AEP[33] ALSN[19,32,45] AMD[32,104] ASML[24,58] AVGO[29] BAC[17,22,75] BB[17,38] CME[21,35] COST[80] CRWD[29,31,42] CSX[18] CVX[25] DIS[18,25,37] DUK[25,27,38] EOG[23] ETN[28] GE[18,40] GOOGL[23,55,89] GS[18] IBM[24,36] INTC[23] INTU[24] JNJ[26,27] KMB[21,39,87,94] LCII[22,30,54] LLY[33] LMT[16,18,80,93] LULU[18,47] META[25,75] MLR[57] MMS[26,30] MP[35] MSFT[25,59] MU[27,60] NKE[36] NOK[17,41] NU[17,50,78] NVO[22,27,64] ODFL[17,21,44,51] PEP[97,110] PGR[23,34,96] PLTR[30,37] PYPL[29,56] ROST[23] RRX[21] RTX[22,33,45,47] SAIC[37] SBUX[40] SCHW[21,37] SFM[24] SMCI[24] SOFI[35] SSD[18,68] TGT[20,34,40] TMO[25,85] TSCO[25,107] TSLA[20] TSM[27,37,64] TTC[29,85] TXRH[19,25,34] UHS[27,76] UNP[27] UPS[17,23,26,47] WDFC[27,85] WSO[19,59] ZTS[30,56]"""
USER = {m.group(1): [int(x) for x in m.group(2).split(',')] for m in re.finditer(r'([A-Z]+)\[([\d,]+)\]', USER_TXT)}
DEN_SHORT = sum(1 for v in USER.values() if any(p <= 33 for p in v)); DEN_LONG = sum(1 for v in USER.values() if any(p > 45 for p in v))   # 61 / 33
PAIRS = [('GS', 39, 18, 0), ('JNJ', 34, 26, 0), ('LMT', 18, 33, 0), ('AVGO', 38, 29, 0), ('LULU', 18, 26, 0), ('SMCI', 24, 37, 0),
         ('TSLA', 20, 29, 0), ('ACN', 32, 25, 0), ('PLTR', 30, 28, 0), ('BAC', 75, 62, 0), ('DIS', 19, 32, 1), ('CRWD', 31, 15, 0)]   # ge=1 表示 ≥
HUMAN_PAIRS = {'LMT', 'ACN', 'DIS'}                       # 已知需要人工判定
CHARTS = [('LULU', 18), ('SMCI', 24), ('GE', 40)]
HANDOVER = dict(pairs=9, short_cand=46, short_final=17, long_cand=16)   # 交接文件第 5 節（只作為「舊實作在今天資料上能否重現」的資訊）
CLASSES = ['MATCH', 'NUMERICAL_TOLERANCE', 'DATA_DIFFERENCE', 'IMPLEMENTATION_BUG', 'RULE_CONFLICT', 'NEEDS_HUMAN_REVIEW', 'HISTORICAL_PROVENANCE_WARNING']
TOL = 1e-9
RAW_FIELDS = [f'{k}@{w}' for w in ('252', '504') for k in ('A_raw_n', 'A_raw', 'A_d2_n', 'A_d2', 'A_rt_n', 'A_rt', 'A_wick')] +              [f'{k}_{y}' for k in ('tg4', 'qday', 'quickfail') for y in ('1y', '2y', '3y')]
HIST_FIELDS = {f'{k}_{y}' for k in ('tg4', 'qday', 'quickfail') for y in ('1y', '2y', '3y')}   # core 對歷史不足的股票把視窗起點夾在 0，frozen 用 N-W（負索引）
PCT_FIELDS = ['p突破', 'p二日', 'p回測', 'p雜訊'] + [f'p快敗_{y}' for y in ('1y', '2y', '3y')]
COMP_FIELDS = [f'p穿插_{y}' for y in ('1y', '2y', '3y')]
SCORE_FIELDS = ['分數_短', '分數_中', '分數_長', '分數']

def fetch_one(a):
    tk, wd, asof, synthetic = a
    if synthetic:
        import hashlib as h, regression_synth as rs
        df = data.normalize(rs.synth(int(h.md5(tk.encode()).hexdigest(), 16) % 10000), asof)
    else:
        err = None
        for k in range(4):
            try: df = data.normalize(data.fetch_yahoo(tk), asof); break
            except Exception as e: err = e; time.sleep(2 * (k + 1))
        else: return tk, str(err)
    df.drop(columns='date').to_csv(Path(wd) / 'data_v' / f'{tk}.csv', index=False); return tk, None

def old_ticker(tk):
    import metrics_v22; return metrics_v22.run_ticker(tk)
def new_ticker(tk):
    df = data.normalize(pd.read_csv(f'data_v/{tk}.csv'), os.environ['ASOF']); return tk, metrics.compute_metrics(df)

def fmtc(cands): return ' '.join(str(c['均線']) + '(' + str(c['分數']) + ')' for c in cands)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]

class Ledger:
    """每個比較的分類計數（summary）＋非 MATCH 的逐列差異（diffs）"""
    def __init__(self, cap=200000): self.cnt = {}; self.diffs = []; self.cap = cap; self.maxabs = {}; self.maxrel = {}
    def add(self, layer, field, cls, n=1, ab=0., rel=0.):
        k = (layer, field); self.cnt.setdefault(k, Counter())[cls] += n
        self.maxabs[k] = max(self.maxabs.get(k, 0.), ab if np.isfinite(ab) else 1e300); self.maxrel[k] = max(self.maxrel.get(k, 0.), rel if np.isfinite(rel) else 1e300)
    def diff(self, row):
        if len(self.diffs) < self.cap: self.diffs.append(row)

def scalar_cls(a, b):
    if a is None or b is None or (isinstance(a, float) and np.isnan(a)) != (isinstance(b, float) and np.isnan(b)): return 'IMPLEMENTATION_BUG', np.nan, np.nan
    if isinstance(a, float) and np.isnan(a): return 'MATCH', 0., 0.
    d = abs(float(a) - float(b)); rel = d / abs(a) if a else (np.inf if d else 0.)
    return ('MATCH' if d == 0 else ('NUMERICAL_TOLERANCE' if (d <= TOL or rel <= TOL) else 'IMPLEMENTATION_BUG')), d, rel

def compare_layer(led, layer, old, new, fields, ctx, note=''):
    """old/new：以 (ticker,period) 為 index 的 DataFrame；向量化比較每個欄位"""
    idx = old.index.union(new.index)
    for f in fields:
        a = old[f].reindex(idx).astype(float); b = new[f].reindex(idx).astype(float)
        both = a.isna() & b.isna(); one = a.isna() ^ b.isna(); d = (a - b).abs()
        match = both | (d == 0); rel = (d / a.abs()).where(a != 0, np.where(d > 0, np.inf, 0.))
        tol = ~match & ~one & ((d <= TOL) | (rel <= TOL)); diff = ~match & ~tol
        led.add(layer, f, 'MATCH', int(match.sum())); led.add(layer, f, 'NUMERICAL_TOLERANCE', int(tol.sum()), float(d[tol].max()) if tol.any() else 0., float(rel[tol].max()) if tol.any() else 0.)
        for key in idx[(tol | diff).to_numpy()]:
            tk, p = key; av, bv, dv, rv = a[key], b[key], d[key], rel[key]
            if key in idx[tol.to_numpy()]: cls = 'NUMERICAL_TOLERANCE'
            elif tk in ctx['data_mismatch']: cls = 'DATA_DIFFERENCE'
            elif f in HIST_FIELDS and tk in ctx['short_hist']: cls = 'RULE_CONFLICT'
            else: cls = 'IMPLEMENTATION_BUG'
            if cls != 'NUMERICAL_TOLERANCE':
                led.add(layer, f, cls, 1, float(dv) if np.isfinite(dv) else 1e300, float(rv) if np.isfinite(rv) else 1e300)
                led.diff(dict(ticker=tk, period=p, layer=layer, field=f, old=av, new=bv, abs_diff=dv, rel_diff=rv, classification=cls, note=note))
        # NUMERICAL_TOLERANCE 也逐列列出（量小），diff 已計入 cnt
    return

def compare_scalar(led, layer, tk, period, field, old, new, note='', force=None):
    cls, ab, rel = scalar_cls(old, new)
    if force and cls != 'MATCH': cls = force
    led.add(layer, field, cls, 1, ab if np.isfinite(ab) else 1e300, rel if np.isfinite(rel) else 1e300)
    if cls != 'MATCH': led.diff(dict(ticker=tk, period=period, layer=layer, field=field, old=old, new=new, abs_diff=ab, rel_diff=rel, classification=cls, note=note))
    return cls

def compare_exact(led, layer, tk, period, field, old, new, note=''):
    cls = 'MATCH' if old == new else 'IMPLEMENTATION_BUG'
    led.add(layer, field, cls, 1)
    if cls != 'MATCH': led.diff(dict(ticker=tk, period=period, layer=layer, field=field, old=old, new=new, abs_diff='', rel_diff='', classification=cls, note=note))
    return cls

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--asof', default='2026-09-24'); ap.add_argument('--out', default='regression'); ap.add_argument('--work')
    ap.add_argument('--only', help='僅供 harness 測試：只跑這些股票（逗號分隔）'); ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--inject-bug', action='store_true', help='僅供自我測試：故意讓新實作偏離，驗證 regression 會判 FAIL'); a = ap.parse_args()
    out = Path(a.out).resolve(); (out / 'charts').mkdir(parents=True, exist_ok=True); wd = Path(a.work or tempfile.mkdtemp(prefix='regwork_')).resolve(); (wd / 'data_v').mkdir(parents=True, exist_ok=True)
    TK = [t for t in TICKERS if not a.only or t in a.only.split(',')]
    os.environ['ASOF'] = a.asof; t0 = time.time(); fetch_fail = []
    with ProcessPoolExecutor(4) as ex:
        for tk, err in ex.map(fetch_one, [(tk, str(wd), a.asof, a.synthetic) for tk in TK]):
            if err: fetch_fail.append((tk, err)); print('DATA_FETCH_FAILURE', tk, err, flush=True)
    tks = [t for t in TK if (wd / 'data_v' / f'{t}.csv').exists()]; print(f'資料 {len(tks)}/{len(TK)} 檔 {time.time()-t0:.0f}s', flush=True)
    os.chdir(wd)
    # ── 舊（frozen）流程：原檔照跑 ──
    import ma_select_v18 as ms
    (wd / 'out_v22').mkdir(exist_ok=True)
    with ProcessPoolExecutor(4) as ex: res = list(ex.map(old_ticker, tks))
    for tk, (M, T) in zip(tks, res): M.to_pickle(f'out_v22/{tk}.pkl')
    pd.concat([T for _, T in res]).to_pickle('tg4.pkl'); print(f'舊 metrics_v22 {time.time()-t0:.0f}s', flush=True)
    runpy.run_path(str(ROOT / 'research' / 'extra_metrics.py'), run_name='__main__')      # 原檔：寫 extra_metrics.pkl
    import composite4; Dold = composite4.build().sort_values(['ticker', 'period']).reset_index(drop=True); Dold.to_pickle('composite2.pkl')   # final_select.py 讀這個檔名
    import final_select as fs
    old_sel = {tk: fs.run(tk) for tk in tks}; print(f'舊流程完成 {time.time()-t0:.0f}s', flush=True)
    # ── 新流程（core/）──
    if a.inject_bug: score.WS['短']['突破'] += .05          # 自我測試用：故意偏離
    with ProcessPoolExecutor(4) as ex: newM = dict(ex.map(new_ticker, tks))
    ref = pd.concat([score.make_features(M).assign(ticker=tk) for tk, M in newM.items()], ignore_index=True)
    S = {tk: score.score_table(M, ref) for tk, M in newM.items()}; new_sel = {}
    dfs = {tk: data.normalize(pd.read_csv(f'data_v/{tk}.csv'), a.asof) for tk in tks}
    for tk in tks: new_sel[tk] = sel.select(dfs[tk], S[tk], **sel.LEGACY)
    print(f'新流程完成 {time.time()-t0:.0f}s', flush=True)
    # ── 比較 ──
    ctx = dict(data_mismatch=set(), short_hist={tk for tk in tks if len(dfs[tk]) < 756})
    for tk in tks:
        o = ms.load(tk); n = dfs[tk]
        if len(o) != len(n) or not np.array_equal(o[['open', 'high', 'low', 'close', 'volume']].to_numpy(float), n[['open', 'high', 'low', 'close', 'volume']].to_numpy(float)): ctx['data_mismatch'].add(tk)
    led = Ledger(); old_idx = Dold.set_index(['ticker', 'period'])
    newS = pd.concat([S[tk].assign(ticker=tk) for tk in tks]).set_index(['ticker', 'period'])
    newRaw = pd.concat([newM[tk].assign(ticker=tk) for tk in tks]).set_index(['ticker', 'period'])
    compare_layer(led, 'raw_metrics', old_idx, newRaw, RAW_FIELDS, ctx)
    raw_bad = any(v.get('IMPLEMENTATION_BUG', 0) + v.get('RULE_CONFLICT', 0) + v.get('DATA_DIFFERENCE', 0) for (l, f), v in led.cnt.items() if l == 'raw_metrics'); up = 'upstream raw_metrics 已有差異' if raw_bad else ''
    compare_layer(led, 'percentile', old_idx, newS, PCT_FIELDS, ctx, up)
    compare_layer(led, 'score_component', old_idx, newS, COMP_FIELDS, ctx, up)
    compare_layer(led, 'composite_score', old_idx, newS, SCORE_FIELDS, ctx, up)
    sel_rows = []; cand_rows = []
    for tk in tks:
        for nm, lo, hi, W in sel.RANGES:
            of, oc = old_sel[tk][nm]; nr = new_sel[tk][nm]; nf, nc = nr['final'], nr['cands']
            os_, ns_ = sorted(c['均線'] for c in oc), sorted(c['均線'] for c in nc)
            c1 = compare_exact(led, 'candidate_set', tk, nm, 'candidate_periods', str(os_), str(ns_), up)
            om = {c['均線']: c for c in oc}; nmap = {c['均線']: c for c in nc}
            for p in sorted(set(om) & set(nmap)):
                for f in ('分數', '簡單報酬', '簡單回撤', '複雜報酬', '複雜回撤', '回測平均'): compare_scalar(led, 'candidate_set', tk, p, f'cand_{f}', float(om[p][f]), float(nmap[p][f]), up)
            c2 = compare_exact(led, 'final_selection', tk, nm, 'final_period', of, nf, up)
            sel_rows.append(dict(ticker=tk, range=nm, old_final=of, new_final=nf, old_candidates=' '.join(f"{c['均線']}({c['分數']})" for c in oc),
                                 new_candidates=' '.join(f"{c['均線']}({c['分數']})" for c in nc), user_periods=' '.join(map(str, USER.get(tk, []))), candidate_set_class=c1, final_class=c2))
    # 2b) 兩兩比較
    human = json.loads((out / 'human_review.json').read_text(encoding='utf-8')) if (out / 'human_review.json').exists() else {}
    pw = []
    for tk, p1, p2, ge in PAIRS:
        if tk not in S: pw.append(dict(ticker=tk, period_a=p1, period_b=p2, classification='DATA_DIFFERENCE', note='no data')); led.add('pairwise', tk, 'DATA_DIFFERENCE'); continue
        og = Dold[Dold.ticker == tk].set_index('period')['分數']; ng = S[tk].set_index('period')['分數']
        osm = dict(zip(og.index, fs.smooth(og.to_numpy()))); nsm = dict(zip(*sel.smoothed_scores(S[tk])))
        rel_ = (lambda x, y: x >= y) if ge else (lambda x, y: x > y)
        res = dict(old=rel_(og[p1], og[p2]), new=rel_(ng[p1], ng[p2]), old_s=rel_(osm[p1], osm[p2]), new_s=rel_(nsm[p1], nsm[p2]))
        cs = [scalar_cls(float(x), float(y))[0] for x, y in ((og[p1], ng[p1]), (og[p2], ng[p2]), (osm[p1], nsm[p1]), (osm[p2], nsm[p2]))]
        worst = max(cs, key=CLASSES.index); same = res['old'] == res['new'] and res['old_s'] == res['new_s']
        cls = worst if same or worst != 'MATCH' else 'IMPLEMENTATION_BUG'
        if not same: cls = 'IMPLEMENTATION_BUG'
        note = ''; basis_ok = same and worst in ('MATCH', 'NUMERICAL_TOLERANCE'); hv = human.get(f'pair_{tk}') if tk in HUMAN_PAIRS else None; hj = 'directional'
        rel_txt = '≥' if ge else '>'; gt_txt = f'{p1} {rel_txt} {p2}'
        if tk in HUMAN_PAIRS:
            if hv == 'TIE': hj = 'approx_tie'; gt_txt = f'{p1} ≈ {p2}（human-confirmed approximate tie）'
            elif hv == 'PASS': gt_txt = f'{p1} {rel_txt} {p2}（human-confirmed）'
            else: gt_txt = f'{p1} ? {p2}（待人工）'
            if not basis_ok: note = '人工已標記，但 old/new 分數不一致（見 composite_score 層）'
            elif hv == 'PASS': cls, note = 'MATCH', 'human-confirmed directional relation'
            elif hv == 'TIE': cls, note = 'MATCH', 'human-confirmed approximate tie'
            else: cls, note = 'NEEDS_HUMAN_REVIEW', '已知需人工判定案例（regression/human_review.json 未標記）'
        led.add('pairwise', tk, cls)
        pw.append(dict(ticker=tk, period_a=p1, period_b=p2, relation='>=' if ge else '>', human_judgment=hj, human_ground_truth=gt_txt, primary_score_basis='smoothed_structural_score',
                       old_smooth_a=osm[p1], old_smooth_b=osm[p2], new_smooth_a=nsm[p1], new_smooth_b=nsm[p2], old_smooth_margin=osm[p1] - osm[p2], new_smooth_margin=nsm[p1] - nsm[p2],
                       old_smooth_holds=res['old_s'], new_smooth_holds=res['new_s'], classification=cls, note=note,
                       raw_unsmoothed_old_a=og[p1], raw_unsmoothed_old_b=og[p2], raw_unsmoothed_new_a=ng[p1], raw_unsmoothed_new_b=ng[p2], raw_old_holds=res['old'], raw_new_holds=res['new'],
                       raw_note='未平滑，診斷用'))
    pd.DataFrame(pw).to_csv(out / 'pairwise_comparison.csv', index=False)
    # 2c) 候選命中率（分母固定 61 / 33）
    hit = []; tot = {k: [0, 0] for k in ('short_cand', 'short_final', 'long_cand', 'long_final')}; tot2 = {'short_cand': [0, 0], 'short_final': [0, 0]}   # tot2＝歷史定義 ±2
    for tk, up_ in USER.items():
        if tk not in tks: continue
        us = [p for p in up_ if p <= 33]; ul = [p for p in up_ if p > 45]
        for kind, ups, nm, near in (('short', us, '短期', 0), ('long', ul, '長期', 5)):
            if not ups: continue
            oc = [c['均線'] for c in old_sel[tk][nm][1]]; nc = [c['均線'] for c in new_sel[tk][nm]['cands']]; of = old_sel[tk][nm][0]; nf = new_sel[tk][nm]['final']
            H = lambda cs: any(abs(p - c) <= near for p in ups for c in cs)
            if kind == 'short':
                H2 = lambda cs: any(abs(p - c) <= 2 for p in ups for c in cs); tot2['short_cand'][0] += H2(oc); tot2['short_cand'][1] += H2(nc); tot2['short_final'][0] += H2([of]); tot2['short_final'][1] += H2([nf])
            oh, nh, ofh, nfh = H(oc), H(nc), H([of]), H([nf]); tot[kind + '_cand'][0] += oh; tot[kind + '_cand'][1] += nh; tot[kind + '_final'][0] += ofh; tot[kind + '_final'][1] += nfh
            hit.append(dict(ticker=tk, range=nm, user_periods=' '.join(map(str, ups)), old_candidates=' '.join(map(str, oc)), new_candidates=' '.join(map(str, nc)),
                            old_cand_hit=oh, new_cand_hit=nh, old_final=of, new_final=nf, old_final_hit=ofh, new_final_hit=nfh, classification='MATCH' if (oh, ofh) == (nh, nfh) and oc == nc and of == nf else 'IMPLEMENTATION_BUG'))
    dens = dict(short_cand=DEN_SHORT, short_final=DEN_SHORT, long_cand=DEN_LONG, long_final=DEN_LONG)
    for k, (o_, n_) in tot.items():
        c = 'MATCH' if o_ == n_ else 'IMPLEMENTATION_BUG'; led.add('candidate_hit_rate', k, c)
        hit.append(dict(ticker='__TOTAL__', range=k, user_periods=f'denominator={dens[k]}', old_cand_hit=o_, new_cand_hit=n_, old_final_hit=o_ if 'final' in k else '', new_final_hit=n_ if 'final' in k else '', classification=c,
                        note=f"handover baseline={HANDOVER.get(k, 'n/a')}"))
    pd.DataFrame(hit).to_csv(out / 'candidate_hit_rate.csv', index=False)
    # 2d) 圖：資料層比較（自動）＋視覺判定（人工）
    import events_v22 as oev, tangle_v4 as ot4
    from core import events as nev, tangle as nt4
    chart_rows = []
    for tk, p in CHARTS:
        if tk not in tks: chart_rows.append(dict(ticker=tk, period=p, classification='DATA_DIFFERENCE', note='no data')); continue
        df = dfs[tk]; O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = ms.wilder_atr(df); ma = df.close.rolling(p).mean().to_numpy(); mp = np.r_[np.nan, ma[:-1]]
        oe = oev.events(O, H, L, C, ma, atr); ne = nev.events(O, H, L, C, ma, atr)
        same = all(repr(x) == repr(y) for x, y in zip(oe, ne)) and repr(ot4.detect(O, H, L, C, ma, mp, atr)) == repr(nt4.detect(O, H, L, C, ma, mp, atr)) and np.array_equal(ot4.qualify(O, H, L, C, ma, mp, atr), nt4.qualify(O, H, L, C, ma, mp, atr))
        led.add('chart_data', f'{tk}_{p}', 'MATCH' if same else 'IMPLEMENTATION_BUG')
        g = S[tk][S[tk].period == p].iloc[0]; go = Dold[(Dold.ticker == tk) & (Dold.period == p)].iloc[0]
        title = f"{tk} SMA{p}｜new 分數 短{g['分數_短']:.1f} 中{g['分數_中']:.1f} 長{g['分數_長']:.1f}（old 短{go['分數_短']:.1f} 中{go['分數_中']:.1f} 長{go['分數_長']:.1f}）｜突破{g['p突破']:.0f} 二日{g['p二日']:.0f} 回測{g['p回測']:.0f} 雜訊{g['p雜訊']:.0f} 穿插1y {g['p穿插_1y']:.0f} 快敗3y {g['p快敗_3y']:.0f}"
        (out / 'charts' / f'{tk}_{p}.png').write_bytes(charts.chart_png(df, p, title))
        conf = human.get(f'chart_{tk}_{p}') == 'PASS'; cls = 'MATCH' if conf else 'NEEDS_HUMAN_REVIEW'; led.add('chart_visual', f'{tk}_{p}', cls)
        chart_rows.append(dict(ticker=tk, period=p, classification=cls, events_and_tangle_data_identical=same, note='human-confirmed' if conf else '圖需人工目視判定（程式不自行宣告 PASS）', title=title))
    # 2e) 交接文件數字能否由「舊實作 + 今天資料」重現（資訊用，不計入 FAIL）
    ok_raw = sum(bool(r['raw_old_holds']) for r in pw if 'raw_old_holds' in r); ok_sm = sum(bool(r['old_smooth_holds']) for r in pw if 'old_smooth_holds' in r)
    base = [('pairs（平滑結構分數，主口徑）', ok_sm, HANDOVER['pairs'], 12, True), ('short_cand（歷史定義 ±2）', tot2['short_cand'][0], HANDOVER['short_cand'], DEN_SHORT, True),
            ('short_final（歷史定義 ±2）', tot2['short_final'][0], HANDOVER['short_final'], DEN_SHORT, True), ('long_cand（±5）', tot['long_cand'][0], HANDOVER['long_cand'], DEN_LONG, True),
            ('pairs（未平滑，診斷用）', ok_raw, HANDOVER['pairs'], 12, False), ('short_cand（完全相等，診斷用）', tot['short_cand'][0], HANDOVER['short_cand'], DEN_SHORT, False),
            ('short_final（完全相等，診斷用）', tot['short_final'][0], HANDOVER['short_final'], DEN_SHORT, False)]
    # HISTORICAL_PROVENANCE_WARNING 只用於「歷史交接文件數字」與「重建舊實作＋今天資料」之間無法完全重現的差異；
    # 前提：current old-vs-new 沒有 IMPLEMENTATION_BUG／RULE_CONFLICT／DATA_DIFFERENCE、沒有資料抓取失敗、人工判定（HUMAN_PAIRS／圖）都已完成。前提不成立時維持 NEEDS_HUMAN_REVIEW，不掩蓋。
    unres_pairs = [r for r in pw if r['classification'] == 'NEEDS_HUMAN_REVIEW']; unres_charts = [r for r in chart_rows if r['classification'] == 'NEEDS_HUMAN_REVIEW']
    nfail0 = sum(c_.get(k_, 0) for c_ in led.cnt.values() for k_ in ('IMPLEMENTATION_BUG', 'RULE_CONFLICT', 'DATA_DIFFERENCE'))
    warn_ok = nfail0 == 0 and not fetch_fail and not unres_pairs and not unres_charts
    mism = [b_ for b_ in base if b_[4] and b_[1] != b_[2]]
    for b_ in mism: led.add('historical_provenance', b_[0], 'HISTORICAL_PROVENANCE_WARNING' if warn_ok else 'NEEDS_HUMAN_REVIEW')
    # ── 輸出 ──
    pd.DataFrame(sel_rows).to_csv(out / 'select_results.csv', index=False); pd.DataFrame(led.diffs, columns=['ticker', 'period', 'layer', 'field', 'old', 'new', 'abs_diff', 'rel_diff', 'classification', 'note']).to_csv(out / 'regression_diffs.csv', index=False)
    rows = []
    for (layer, f), c in sorted(led.cnt.items()):
        rows.append(dict(layer=layer, field=f, n_compared=sum(c.values()), **{k: c.get(k, 0) for k in CLASSES}, max_abs_diff=led.maxabs.get((layer, f), 0.), max_rel_diff=led.maxrel.get((layer, f), 0.)))
    SM = pd.DataFrame(rows); SM.to_csv(out / 'regression_summary.csv', index=False)
    tot_c = SM[CLASSES].sum(); nfail = int(tot_c['IMPLEMENTATION_BUG'] + tot_c['RULE_CONFLICT'] + tot_c['DATA_DIFFERENCE']); nhr = int(tot_c['NEEDS_HUMAN_REVIEW']); nwarn = int(tot_c['HISTORICAL_PROVENANCE_WARNING'])
    correctness = 'FAIL' if (nfail or fetch_fail) else 'PASS'; human_status = 'INCOMPLETE' if nhr else 'COMPLETE'
    L_ = []; P = L_.append
    P(f'REGRESSION_CORRECTNESS: {correctness}\nHUMAN_REVIEW_STATUS: {human_status}\nHISTORICAL_PROVENANCE_WARNINGS: {nwarn}\n')
    P(f'MATCH/PASS: {int(tot_c["MATCH"])}\nNUMERICAL_TOLERANCE: {int(tot_c["NUMERICAL_TOLERANCE"])}\nFAIL: {nfail}（IMPLEMENTATION_BUG {int(tot_c["IMPLEMENTATION_BUG"])}、RULE_CONFLICT {int(tot_c["RULE_CONFLICT"])}、DATA_DIFFERENCE {int(tot_c["DATA_DIFFERENCE"])}）\n'
      f'NEEDS_HUMAN_REVIEW: {nhr}\nHISTORICAL_PROVENANCE_WARNING: {nwarn}\nDATA_FETCH_FAILURE: {len(fetch_fail)}\n')
    P(f'# Regression 報告（frozen 舊實作 vs core 新實作，asof={a.asof}，{len(tks)}/{len(TK)} 檔{"，SYNTHETIC 資料" if a.synthetic else ""}{"，INJECT-BUG 自我測試" if a.inject_bug else ""}）\n')
    P('計數單位＝逐格比較（ticker × 均線 × 欄位）；圖與人工判定案例各算 1。基準＝這批股票自己（同 composite4）。使用者人工答案：' + f'{len(USER)} 檔有標記，短期分母 {DEN_SHORT}、長期分母 {DEN_LONG}。\n')
    P('## 分層結果\n\n| 層 | 比較數 | MATCH | NUMERICAL_TOLERANCE | DATA_DIFFERENCE | IMPLEMENTATION_BUG | RULE_CONFLICT | NEEDS_HUMAN_REVIEW |\n|---|---|---|---|---|---|---|---|')
    for layer, g in SM.groupby('layer', sort=False): P(f'| {layer} | {int(g.n_compared.sum())} | ' + ' | '.join(str(int(g[k].sum())) for k in CLASSES) + ' |')
    P('\n## 來源完整性\n')
    for nm_, oldf, newf in (('events', 'research/events_v22.py', 'core/events.py'), ('tangle', 'research/tangle_v4.py', 'core/tangle.py'), ('backtest', 'research/bt_engine_v1.py', 'core/backtest.py')):
        P(f'- {oldf}（{sha(ROOT/oldf)}）vs {newf}（{sha(ROOT/newf)}）：' + ('位元組相同' if sha(ROOT / oldf) == sha(ROOT / newf) else '不同（backtest 只多 return_eq 選用參數，見 git diff）'))
    try:
        for f in ('events_v22', 'tangle_v4', 'bt_engine_v1'): P(f'- research/{f}.py 與首次上傳 commit 4728067 的原檔：' + ('相同' if subprocess.run(['git', 'show', f'4728067:{f}.py'], cwd=ROOT, capture_output=True).stdout == (ROOT / 'research' / f'{f}.py').read_bytes() else '不同或無法驗證'))
    except Exception as e: P(f'- git 原檔比對略過：{e}')
    P('- research/metrics_v22.py 不在 Drive，依交接 7-2 重建（tg4 依文字說明）；research/ma_select_v18.py 為 7-1 逐字 shim；research/bt_engine.py 為 final_select 所需別名。extra_metrics 的 cross_* 欄位 core 未實作（不參與分數），未比較。')
    if ctx['data_mismatch']: P(f'- **DATA_DIFFERENCE：新舊載入的資料不同的股票**：{sorted(ctx["data_mismatch"])}')
    if ctx['short_hist']: P(f'- 資料 <756 根的股票（tg4／qday／quickfail 視窗規則 RULE_CONFLICT 適用）：{sorted(ctx["short_hist"])}')
    P('\n## 兩兩比較（old＝frozen composite4，new＝core；主口徑＝平滑結構分數）\n')
    P('Pairwise human review uses smoothed structural scores because production candidate selection and Rule B use smoothed structural scores. Raw scores are retained only for diagnostics.\n')
    P('| 股票 | human ground truth | old smooth A/B | new smooth A/B | 平滑分差 A−B（new） | 平滑方向與人工一致？（資訊） | classification |\n|---|---|---|---|---|---|---|')
    for r in pw:
        if 'old_smooth_a' not in r: continue
        agree = '—（人工判定為近似平手）' if r['human_judgment'] == 'approx_tie' else ('是' if r['new_smooth_holds'] else '否')
        P(f"| {r['ticker']} | {r['human_ground_truth']} | {r['old_smooth_a']:.2f} / {r['old_smooth_b']:.2f} | {r['new_smooth_a']:.2f} / {r['new_smooth_b']:.2f} | {r['new_smooth_margin']:+.2f} | {agree} | {r['classification']}{'（' + r['note'] + '）' if r['note'] and r['ticker'] in HUMAN_PAIRS else ''} |")
    P('\n「平滑方向與人工一致？」只是資訊：regression 檢查的是 old 與 new 是否相同；人工判定不是由程式分數決定，也不因程式分數而改寫。')
    P('\n### 診斷：未平滑分數（raw，診斷用，不作為 production 口徑）\n\n| 股票 | 比較 | old A/B（未平滑，診斷用） | new A/B（未平滑，診斷用） |\n|---|---|---|---|')
    for r in pw:
        if 'raw_unsmoothed_old_a' in r: P(f"| {r['ticker']} | {r['period_a']}{r['relation']}{r['period_b']} | {r['raw_unsmoothed_old_a']:.2f} / {r['raw_unsmoothed_old_b']:.2f} | {r['raw_unsmoothed_new_a']:.2f} / {r['raw_unsmoothed_new_b']:.2f} |")
    P('\n## 候選命中率（old vs new；不以「較高」作為 PASS 理由）\n\n| 項目 | old | new | 分母 | 交接文件數字 | 分類 |\n|---|---|---|---|---|---|')
    for k, (o_, n_) in tot.items(): P(f"| {k}（{'±5' if k.startswith('long') else '完全相等'}） | {o_} | {n_} | {dens[k]} | {HANDOVER.get(k, 'n/a') if k.startswith('long') else '（見 ±2 列）'} | {'MATCH' if o_ == n_ else 'IMPLEMENTATION_BUG'} |")
    for k, (o_, n_) in tot2.items(): P(f"| {k}（歷史定義 ±2） | {o_} | {n_} | {dens[k]} | {HANDOVER[k]} | {'MATCH' if o_ == n_ else 'IMPLEMENTATION_BUG'} |")
    P('\n## 舊實作＋今天資料能否重現交接文件數字（資訊；主列不一致者計為 HISTORICAL_PROVENANCE_WARNING，診斷列不計）\n\n歷史短期命中定義已由原始 snapshot 確認為 ±2；短期差異來源見 regression/snapshot/snapshot_regression_report.md（ACN 為主要未解差異）。\n\n| 項目 | 舊實作今天結果 | 交接文件 | 是否一致 | 計入 |\n|---|---|---|---|---|')
    for nm_, v, b, d_, cnt in base: P(f'| {nm_} | {v}/{d_} | {b}/{d_} | {"一致" if v == b else "**不一致**"} | {"是" if cnt else "否（診斷）"} |')
    P('\n## 人工判定狀態\n')
    unres_pairs = [r for r in pw if r['classification'] == 'NEEDS_HUMAN_REVIEW']; unres_charts = [r for r in chart_rows if r['classification'] == 'NEEDS_HUMAN_REVIEW']
    P(f'- HUMAN_PAIRS unresolved：{len(unres_pairs)}；chart_visual unresolved：{len(unres_charts)}')
    for r in pw:
        if r['ticker'] in HUMAN_PAIRS and 'human_ground_truth' in r: P(f"- 兩兩比較 {r['ticker']}：{r['human_ground_truth']}；new 平滑分 {r['new_smooth_a']:.2f}/{r['new_smooth_b']:.2f}；{r['classification']}（{r['note']}）")
    for tk in HUMAN_PAIRS & set(tks):
        for nm in ('短期', '長期'): P(f"  - {tk} {nm} old 候選：{fmtc(old_sel[tk][nm][1])} → 選 {old_sel[tk][nm][0]}；new 候選：{fmtc(new_sel[tk][nm]['cands'])} → 選 {new_sel[tk][nm]['final']}")
    for r in chart_rows: P(f"- 圖 charts/{r['ticker']}_{r['period']}.png：{r['classification']}（{r['note']}；事件／糾結資料 old=new：{r.get('events_and_tangle_data_identical')}）")
    P('\n### NEEDS_HUMAN_REVIEW 項目\n' + ('\n'.join([f"- 兩兩比較 {r['ticker']}：尚未在 human_review.json 標記" for r in unres_pairs] + [f"- 圖 {r['ticker']}_{r['period']}：尚未在 human_review.json 標記" for r in unres_charts] + [f'- 交接文件數字重現（{b_[0]}）：{b_[1]}/{b_[3]} vs {b_[2]}/{b_[3]}（因 correctness 或人工判定未完成，不能標為 warning）' for b_ in mism if not warn_ok]) if nhr else '- 無（HUMAN_PAIRS 與 chart_visual 皆已人工確認）'))
    SRC = {'pairs': '評分口徑不明：未平滑 11/12、平滑 8/12 都不是 9/12；LMT、ACN 兩組平滑分差極薄（−1.27、+1.19），單一事件結果不同即可翻轉（見 diagnostics/diagnose_report.md）',
           'short_cand': '已知主要差異來源＝ACN 的歷史 snapshot drift：原始 snapshot 的 ACN 候選 {16,19}、final 16；今天候選 {16,29,19,33}、final 33。資料截止日變體與單一事件都無法重現（見 regression/snapshot/snapshot_regression_report.md）',
           'short_final': '同上（ACN：原始 snapshot final 16，今天 33）', 'long_cand': '見 snapshot 報告'}
    P('\n## Historical provenance warnings\n')
    P('HISTORICAL_PROVENANCE_WARNING 只用於「歷史交接文件／歷史 snapshot」與「重建的舊實作＋今天資料」之間無法完全重現的差異。它不用於 implementation bug、rule conflict、資料抓取失敗、current old-vs-new mismatch 或尚未完成的人工判定，也不影響 production correctness；前提不成立時，這些項目會維持 NEEDS_HUMAN_REVIEW。\n')
    if mism and warn_ok:
        P('| metric | current reconstructed value | handover value | known source / evidence | why this does not imply current implementation failure | resolution status |\n|---|---|---|---|---|---|')
        why = f'frozen research 與 core 的逐層比較（raw_metrics → final_selection）IMPLEMENTATION_BUG {int(tot_c["IMPLEMENTATION_BUG"])}、RULE_CONFLICT {int(tot_c["RULE_CONFLICT"])}、DATA_DIFFERENCE {int(tot_c["DATA_DIFFERENCE"])}；此差異存在於「重建的舊實作＋今天資料」與「歷史數字」之間，不是 old-vs-new 差異；人工判定項目皆已完成'
        for b_ in mism: P(f"| {b_[0]} | {b_[1]}/{b_[3]} | {b_[2]}/{b_[3]} | {SRC[b_[0].split('（')[0]]} | {why} | UNRESOLVED HISTORICAL PROVENANCE |")
        P(f'\n本報告不聲稱已找到真正的歷史原因；{len(mism)} 項都維持 UNRESOLVED HISTORICAL PROVENANCE，原始數字未修改。')
    else: P('- ' + ('無（所有歷史數字都可重現）' if not mism else '有不一致，但 correctness 或人工判定未完成，因此不能標為 warning（見上方 NEEDS_HUMAN_REVIEW 項目）'))
    P('\n人工確認方式：在 regression/human_review.json 寫入 `"chart_LULU_18": "PASS"`、`"pair_LMT": "PASS"`（人工確認指定方向成立）或 `"pair_ACN": "TIE"`（人工確認近似平手，不解讀為任一方向勝出）後重跑 workflow。')
    if fetch_fail: P('\n## DATA_FETCH_FAILURE\n' + '\n'.join(f'- {t}: {e}' for t, e in fetch_fail))
    P('\n## 差異列表\n\n非 MATCH 的逐列差異（ticker、period、field、old、new、abs_diff、rel_diff、classification）見 regression_diffs.csv（前 5 筆非容差差異如下）：\n')
    bad = [d for d in led.diffs if d['classification'] != 'NUMERICAL_TOLERANCE'][:5]
    for d in bad: P(f"- {d['layer']} {d['ticker']} p={d['period']} {d['field']}: old={d['old']} new={d['new']} → {d['classification']} {d['note']}")
    (out / 'regression_report.md').write_text('\n'.join(L_), encoding='utf-8'); print('\n'.join(L_)); return 0

if __name__ == '__main__': sys.exit(main())
