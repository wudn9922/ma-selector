"""單一股票的「建議均線」摘要（給 Atlas 圖表用的 JSON）：與網頁預設完全相同的 production 流程
（SMA、預設權重、gap=15、多空反手、規則 B＋短期 STRUCTURAL_RESCUE_10PT_10PP），只是把結果整理成可序列化的 dict。
不改任何規則；資料不足（< MIN_BARS 根）回傳 None。
VERSION 3（只多欄位，VERSION 2 的欄位名稱與意義不變）：market／costPct（回測用的來回成本，%；台股 0.585、美股 0.1，見 core/market.py）／referencePool（分數對哪個基準池排名）／
adjusted（價格是否已還原股利）／scoring（分數模式，由 score.PCT_MODE＋select.SMOOTH_MODE 組成）；每個區間多 unsuitable（候選中最高反手報酬 ≤ 0）、
held／previousFinal／computedFinal（批次用的 hysteresis：prev＝上一次發佈的 JSON；規則見 _hold，只在設定簽章相同時才會沿用舊 final；v2 區塊不套用）。
VERSION 2 另附（只顯示，與網頁同源）：股票層級排名（core/standardize.py）、短中期候選的近2年分數(參考)、實驗選線 v2（core/select_v2.py）。
這三項需要對應的基準（ref_bests／ref_v2／ref_bests_v2）；沒給就不輸出該欄，production 欄位逐項不變。"""
import math
import numpy as np
from . import metrics, score, select as sel, score_v2, select_v2, standardize, events as ev
from .data import wilder_atr
from .ma import moving_average
from .market import market_of, COSTS
MIN_BARS, FULL_BARS = 250 + 126, 756 + 110       # 與 app.py 相同：太少不算；不足 FULL_BARS 標記 limited（中長期視窗不足）
RANGE_KEYS = {'短期': 'short', '中期': 'medium', '長期': 'long'}
VERSION = 3
HYST_POINTS = 5.0                                  # hysteresis：新 final 的結構分比舊 final 高出不到 5.0 分，就沿用舊 final（未調參，沿用 rescue 10 分的一半）
SIG_KEYS = ('scoring', 'referencePool', 'adjusted', 'costPct', 'kind')   # 設定簽章：上一次檔案與這次完全相同才允許沿用舊 final

def scoring_id(): return f'{score.PCT_MODE}+{sel.SMOOTH_MODE}'          # 例：period+range；recommend 用的就是這兩個預設

def _num(x, nd=4):
    if x is None: return None
    x = float(x); return None if math.isnan(x) or math.isinf(x) else round(x, nd)

def _rank(values, x):
    """x 在基準值 values 中贏過幾 %（standardize.rank_pct，同網頁）→ dict(pct, n)"""
    pc, n = standardize.rank_pct(values, x); return dict(pct=_num(pc, 1), n=int(n))

def _sar(c, suffix=''):
    return dict(sarReturn=_num(c['反手報酬' + suffix]), sarDrawdown=_num(c['反手回撤']), sarWinRate=_num(c['反手勝率']), sarTrades=int(c['反手筆數']))

def _v2(df, M, ref_v2, long_final, ref_bests_v2, cost=ev.COST):
    """實驗選線 v2（尚未驗證，只顯示）：短期 SMA15–45 近 2 年選 2 條、中期 SMA46–70 近 3 年選 1 條、長期同現行"""
    out = select_v2.select_v2(df, M, ref_v2, cost=cost)
    sh, md, su = out['短期'], out['中期'], out['suitability']
    cand_s = lambda c: dict(period=int(c['均線']), score2y=_num(c['結構分'], 1), score1y=_num(c['分數_1y'], 1), sarReturn1y=_num(c['反手報酬_1y']), **_sar(c))
    v2 = dict(
        short=dict(min=select_v2.SHORT[0], max=select_v2.SHORT[1], windowYears=2, final1=int(sh['final1']), final2=None if sh['final2'] is None else int(sh['final2']),
                   secondSource=sh['second_source'], best2y=_num(sh['best_2y'], 1), best1y=_num(sh['best_1y'], 1),
                   candidates=[cand_s(c) for c in sh['cands']], relaxed=[cand_s(c) for c in sh['relaxed']]),
        medium=dict(min=select_v2.MID[0], max=select_v2.MID[1], windowYears=3, final=int(md['final']), best3y=_num(md['best_3y'], 1),
                    candidates=[dict(period=int(c['均線']), score3y=_num(c['結構分'], 1), **_sar(c)) for c in md['cands']]),
        long=dict(final=int(long_final)),
        suitability=dict(short2y=_num(su['short_2y'], 1), short1y=_num(su['short_1y'], 1), mid3y=_num(su['mid_3y'], 1)))
    if ref_bests_v2 is not None:
        v2['rank'] = {k: _rank(ref_bests_v2[c].to_numpy(float), su[c]) for k, c in (('short2y', 'short_2y'), ('short1y', 'short_1y'), ('mid3y', 'mid_3y'))}
    return v2

def _prev_final(prev, key):
    """上一次發佈的 JSON（dict 或 None）中某區間的 final（整數）；沒有／格式不對 → None"""
    if not isinstance(prev, dict) or not isinstance(prev.get('ranges'), list): return None
    for g in prev['ranges']:
        if isinstance(g, dict) and g.get('key') == key:
            p = g.get('final'); return p if isinstance(p, int) and not isinstance(p, bool) else None
    return None

def _hold(f, p0, lo, hi, cands, s0, best, stats0):
    """hysteresis 判斷（純函式）：保留舊 final p0、不換成新算出的 f，要「全部」成立：
    p0 在區間內且 ≠ f；p0 的平滑結構分 s0 ≥ 區間最高 best − GAP（仍是候選等級）；p0 的反手報酬 ≥ 候選最高 − 5pp（仍是規則 B finalist）；
    f 的結構分 − s0 < HYST_POINTS。stats0＝呼叫後才算 p0 的反手回測（只在前面的條件都過了才需要）→ 回傳 (是否保留, p0 的候選 dict 或 None)"""
    if p0 is None or not lo <= p0 <= hi or p0 == f or s0 < best - sel.GAP: return False, None
    cf = next(c for c in cands if c['均線'] == f)
    if not cf['結構分'] - s0 < HYST_POINTS: return False, None
    c0 = next((c for c in cands if c['均線'] == p0), None) or stats0(p0)
    return c0['反手報酬'] >= max(c['反手報酬'] for c in cands) - sel.SAR_PP, c0

def recommend(df, ref, ticker, kind='SMA', reference_asof=None, ref_bests=None, ref_v2=None, ref_bests_v2=None, prev=None, ref_pool='US', ref_pool_v2=None):
    """df：data.normalize 後的日K；ref：基準分佈（reference.parquet）。回傳 dict 或 None（資料不足）
    ref_bests＝standardize.ref_stock_bests(ref)；ref_v2＝reference_v2.parquet；ref_bests_v2＝standardize.ref_stock_bests_v2(ref_v2)（都可省略）
    ref_pool／ref_pool_v2：呼叫端實際傳入的基準池（'TW'／'US'，只是記錄；沒給＝美股池，同過去；ref_pool_v2 沒給＝同 ref_pool）。
    prev＝同一檔上一次發佈的 JSON（dict）或 None；只有批次用，網頁沒有。回測成本依 market_of(ticker)（core/market.py）。"""
    N = len(df)
    if N < MIN_BARS: return None
    mkt = market_of(ticker); cost = COSTS[mkt]
    M = metrics.compute_metrics(df, kind=kind); S = score.score_table(M, ref); R = sel.select(df, S, kind=kind, cost=cost); suit_s, suit_l = sel.suitability(S)
    head = dict(market=mkt, costPct=_num(cost * 100), referencePool=ref_pool, adjusted=bool(df.attrs.get('adjusted', False)), scoring=scoring_id())
    same = isinstance(prev, dict) and all(prev.get(k) == v for k, v in {**head, 'kind': kind}.items() if k in SIG_KEYS)   # 設定簽章相同才可能沿用舊 final
    P, Ss = sel.smoothed_scores(S); sc = dict(zip(P.tolist(), Ss.tolist())); O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df)
    sc2y = None
    if ref_v2 is not None and kind == 'SMA':   # 近2年分數(參考)＝v2 的 分數_2y（短期公式、SMA15–110 整條平滑），同網頁 calc_score2y
        T = score_v2.score_table_v2(M, ref_v2).sort_values('period'); sc2y = dict(zip(T['period'].tolist(), sel.smooth(T['分數_2y'].to_numpy()).tolist()))
    bests = standardize.range_bests(S) if ref_bests is not None else None
    ranges = []
    for nm, lo, hi, W in sel.RANGES:
        r = R[nm]; with2y = sc2y is not None and nm != '長期'; f = int(r['final']); cands = list(r['cands']); p0 = _prev_final(prev, RANGE_KEYS[nm])
        def stats0(p, W=W):   # 舊 final 不在候選裡：補算它的回測（同 select 的視窗、成本）
            a = sel.sar_stats(O, H, L, C, atr, moving_average(df.close, p, kind), max(N - W, 0), cost=cost)
            return {'均線': p, '結構分': sc[p], '反手報酬': a['報酬'], '反手回撤': a['回撤'], '反手勝率': a['勝率'], '反手筆數': a['筆數']}
        best_u = float(Ss[(P >= lo) & (P <= hi)].max())      # 未四捨五入的區間最高分（select 的 best 是四捨五入後）
        held, c0 = _hold(f, p0, lo, hi, cands, sc.get(p0, -np.inf), best_u, stats0) if same else (False, None)
        if held and all(c['均線'] != p0 for c in cands): cands.append(c0)   # final 一定要在 candidates 裡
        g = dict(key=RANGE_KEYS[nm], label=nm, min=lo, max=hi, windowYears=W // 252, final=p0 if held else f, best=_num(r['best'], 1),
                 candidates=[dict(period=int(c['均線']), score=_num(c['結構分'], 1), **({'score2y': _num(sc2y[c['均線']], 1)} if with2y else {}), **_sar(c))
                             for c in cands],
                 unsuitable=bool(max(c['反手報酬'] for c in cands) <= 0), held=bool(held), previousFinal=p0, computedFinal=f)
        if bests is not None: g['rank'] = dict(best=_num(bests[nm], 1), **_rank(ref_bests[nm].to_numpy(float), bests[nm]))
        ranges.append(g)
    out = dict(version=VERSION, ticker=ticker, kind=kind, **head, asof=str(df.date.iloc[-1].date()), bars=N, limited=N < FULL_BARS, referenceAsof=reference_asof,
               suitability=dict(short=_num(suit_s, 1), long=_num(suit_l, 1)), ranges=ranges)
    if ref_v2 is not None and kind == 'SMA':   # v2 區塊是實驗功能，不套用 hysteresis（long.final 是這次算出的，不是沿用的）
        out['v2'] = _v2(df, M, ref_v2, R['長期']['final'], ref_bests_v2, cost); out['v2']['referencePool'] = ref_pool_v2 or ref_pool
    return out
