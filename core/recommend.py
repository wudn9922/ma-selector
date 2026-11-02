"""單一股票的「建議均線」摘要（給 Atlas 圖表用的 JSON）：與網頁預設完全相同的 production 流程
（SMA、預設權重、gap=15、多空反手、規則 B＋短期 STRUCTURAL_RESCUE_10PT_10PP），只是把結果整理成可序列化的 dict。
不改任何規則；資料不足（< MIN_BARS 根）回傳 None。
VERSION 2 另附（只顯示，與網頁同源）：股票層級排名（core/standardize.py）、短中期候選的近2年分數(參考)、實驗選線 v2（core/select_v2.py）。
這三項需要對應的基準（ref_bests／ref_v2／ref_bests_v2）；沒給就不輸出該欄，production 欄位逐項不變。"""
import math
from . import metrics, score, select as sel, score_v2, select_v2, standardize
MIN_BARS, FULL_BARS = 250 + 126, 756 + 110       # 與 app.py 相同：太少不算；不足 FULL_BARS 標記 limited（中長期視窗不足）
RANGE_KEYS = {'短期': 'short', '中期': 'medium', '長期': 'long'}
VERSION = 2

def _num(x, nd=4):
    if x is None: return None
    x = float(x); return None if math.isnan(x) or math.isinf(x) else round(x, nd)

def _rank(values, x):
    """x 在基準值 values 中贏過幾 %（standardize.rank_pct，同網頁）→ dict(pct, n)"""
    pc, n = standardize.rank_pct(values, x); return dict(pct=_num(pc, 1), n=int(n))

def _sar(c, suffix=''):
    return dict(sarReturn=_num(c['反手報酬' + suffix]), sarDrawdown=_num(c['反手回撤']), sarWinRate=_num(c['反手勝率']), sarTrades=int(c['反手筆數']))

def _v2(df, M, ref_v2, long_final, ref_bests_v2):
    """實驗選線 v2（尚未驗證，只顯示）：短期 SMA15–45 近 2 年選 2 條、中期 SMA46–70 近 3 年選 1 條、長期同現行"""
    out = select_v2.select_v2(df, M, ref_v2)
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

def recommend(df, ref, ticker, kind='SMA', reference_asof=None, ref_bests=None, ref_v2=None, ref_bests_v2=None):
    """df：data.normalize 後的日K；ref：基準分佈（reference.parquet）。回傳 dict 或 None（資料不足）
    ref_bests＝standardize.ref_stock_bests(ref)；ref_v2＝reference_v2.parquet；ref_bests_v2＝standardize.ref_stock_bests_v2(ref_v2)（都可省略）"""
    N = len(df)
    if N < MIN_BARS: return None
    M = metrics.compute_metrics(df, kind=kind); S = score.score_table(M, ref); R = sel.select(df, S, kind=kind); suit_s, suit_l = sel.suitability(S)
    sc2y = None
    if ref_v2 is not None and kind == 'SMA':   # 近2年分數(參考)＝v2 的 分數_2y（短期公式、SMA15–110 整條平滑），同網頁 calc_score2y
        T = score_v2.score_table_v2(M, ref_v2).sort_values('period'); sc2y = dict(zip(T['period'].tolist(), sel.smooth(T['分數_2y'].to_numpy()).tolist()))
    bests = standardize.range_bests(S) if ref_bests is not None else None
    ranges = []
    for nm, lo, hi, W in sel.RANGES:
        r = R[nm]; with2y = sc2y is not None and nm != '長期'
        g = dict(key=RANGE_KEYS[nm], label=nm, min=lo, max=hi, windowYears=W // 252, final=int(r['final']), best=_num(r['best'], 1),
                 candidates=[dict(period=int(c['均線']), score=_num(c['結構分'], 1), **({'score2y': _num(sc2y[c['均線']], 1)} if with2y else {}), **_sar(c))
                             for c in r['cands']])
        if bests is not None: g['rank'] = dict(best=_num(bests[nm], 1), **_rank(ref_bests[nm].to_numpy(float), bests[nm]))
        ranges.append(g)
    out = dict(version=VERSION, ticker=ticker, kind=kind, asof=str(df.date.iloc[-1].date()), bars=N, limited=N < FULL_BARS, referenceAsof=reference_asof,
               suitability=dict(short=_num(suit_s, 1), long=_num(suit_l, 1)), ranges=ranges)
    if ref_v2 is not None and kind == 'SMA': out['v2'] = _v2(df, M, ref_v2, R['長期']['final'], ref_bests_v2)
    return out
