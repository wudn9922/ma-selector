"""單一股票的「建議均線」摘要（給 Atlas 圖表用的 JSON）：與網頁預設完全相同的 production 流程
（SMA、預設權重、gap=15、多空反手、規則 B＋短期 STRUCTURAL_RESCUE_10PT_10PP），只是把結果整理成可序列化的 dict。
不改任何規則；資料不足（< MIN_BARS 根）回傳 None。"""
import math
from . import metrics, score, select as sel
MIN_BARS, FULL_BARS = 250 + 126, 756 + 110       # 與 app.py 相同：太少不算；不足 FULL_BARS 標記 limited（中長期視窗不足）
RANGE_KEYS = {'短期': 'short', '中期': 'medium', '長期': 'long'}
VERSION = 1

def _num(x, nd=4):
    x = float(x); return None if math.isnan(x) or math.isinf(x) else round(x, nd)

def recommend(df, ref, ticker, kind='SMA', reference_asof=None):
    """df：data.normalize 後的日K；ref：基準分佈（reference.parquet）。回傳 dict 或 None（資料不足）"""
    N = len(df)
    if N < MIN_BARS: return None
    S = score.score_table(metrics.compute_metrics(df, kind=kind), ref); R = sel.select(df, S, kind=kind); suit_s, suit_l = sel.suitability(S)
    ranges = []
    for nm, lo, hi, W in sel.RANGES:
        r = R[nm]
        ranges.append(dict(key=RANGE_KEYS[nm], label=nm, min=lo, max=hi, windowYears=W // 252, final=int(r['final']), best=_num(r['best'], 1),
                           candidates=[dict(period=int(c['均線']), score=_num(c['結構分'], 1), sarReturn=_num(c['反手報酬']), sarDrawdown=_num(c['反手回撤']),
                                            sarWinRate=_num(c['反手勝率']), sarTrades=int(c['反手筆數'])) for c in r['cands']]))
    return dict(version=VERSION, ticker=ticker, kind=kind, asof=str(df.date.iloc[-1].date()), bars=N, limited=N < FULL_BARS, referenceAsof=reference_asof,
                suitability=dict(short=_num(suit_s, 1), long=_num(suit_l, 1)), ranges=ranges)
