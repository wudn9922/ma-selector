"""hysteresis（core/recommend.py::_hold／recommend(prev=)）與 unsuitable 旗標的測試（合成股價；平滑結構分與反手報酬用 monkeypatch 精確控制，方法同 tests/test_select_rescue.py）
條件（全部成立才沿用舊 final p0）：設定簽章相同、p0 在區間內且 ≠ 新 final f、p0 結構分 ≥ 最高 − gap、p0 反手報酬 ≥ 候選最高 − 5pp、f 結構分 − p0 結構分 < HYST_POINTS
用法：python tests/test_hysteresis.py"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, metrics, score, select as sel, recommend as rec
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

REF = pd.read_parquet(ROOT / 'data' / 'reference.parquet'); DF = data.normalize(synth(7)); PERIODS = np.arange(15, 111)
M0 = metrics.compute_metrics(DF)
SIG = dict(scoring='period+range', referencePool='US', adjusted=False, costPct=0.1, kind='SMA')
def prev_of(short=None, medium=36, long=80, **over):
    """上一次發佈的 JSON（只含 hysteresis 會讀的欄位）；over 覆寫簽章欄位（None＝刪掉該欄）"""
    sig = {**SIG, **over}; sig = {k: v for k, v in sig.items() if v is not None}
    return dict(version=3, ticker='TEST', **sig, ranges=[dict(key=k, final=v) for k, v in (('short', short), ('medium', medium), ('long', long)) if v is not None])

def run(scores, sars, prev=None, ticker='TEST', **kw):
    """scores／sars：{period: 值}（沒列出＝0）。metrics 用快取（recommend 內每次重算太慢）；回傳 (recommend 結果, sar_stats 被呼叫的週期集合)"""
    sm = np.array([float(scores.get(int(p), 0.)) for p in PERIODS]); calls = []
    def fake_smoothed(S, *a, **k): return PERIODS.copy(), sm.copy()
    def fake_sar(O, H, L, C, atr, ma, lo, cost=0.001):
        p = int(np.isnan(ma).sum()) + 1; calls.append(p); return dict(報酬=float(sars.get(p, 0.)), 回撤=-0.1, 勝率=0.5, 筆數=10)
    o = (metrics.compute_metrics, sel.smoothed_scores, sel.sar_stats); metrics.compute_metrics = lambda df, kind='SMA': M0; sel.smoothed_scores, sel.sar_stats = fake_smoothed, fake_sar
    try: return rec.recommend(DF, REF, ticker, prev=prev, **kw), calls
    finally: metrics.compute_metrics, sel.smoothed_scores, sel.sar_stats = o
def short(r): return r['ranges'][0]
def cp(g): return [c['period'] for c in g['candidates']]

# 基本盤：短期候選 20(60)、24(58)、30(52)；反手 .50／.50／.40 → 規則 B finalists＝20、24 → f＝20（結構分最高）
BASE_S = {20: 60., 24: 58., 30: 52.}; BASE_R = {20: .50, 24: .50, 30: .40}
def test_no_prev_and_fields():
    r, _ = run(BASE_S, BASE_R); g = short(r)
    check(g['final'] == 20 and g['computedFinal'] == 20 and g['held'] is False and g['previousFinal'] is None, f"沒有 prev：final＝computedFinal＝20、held False、previousFinal None")
    check(r['version'] == 3 and r['market'] == 'US' and r['costPct'] == 0.1 and r['referencePool'] == 'US' and r['adjusted'] is False and r['scoring'] == 'period+range', 'VERSION 3 頂層欄位')
    for bad in (None, {}, [], 'x', {'ranges': 5}, {'ranges': [None]}, prev_of(short='20'), prev_of(short=True)):
        r2, _ = run(BASE_S, BASE_R, prev=bad); check(short(r2)['held'] is False and short(r2)['previousFinal'] is None and short(r2)['final'] == 20, f'prev 格式不對 {str(bad)[:40]!r} → 當成沒有（不當機、不沿用）')

def test_hold():
    r, _ = run(BASE_S, BASE_R, prev=prev_of(short=24)); g = short(r)
    check(g['final'] == 24 and g['computedFinal'] == 20 and g['held'] is True and g['previousFinal'] == 24, f"p0=24：結構分差 2.0 < 5、仍是 finalist → 沿用 24（computedFinal 20）")
    check(24 in cp(g) and cp(g) == [20, 24, 30], f"final 在 candidates 裡：{cp(g)}")
    r, _ = run({**BASE_S, 40: 60., 90: 60.}, BASE_R, prev=prev_of(short=24)); check(short(r)['held'] and [g['held'] for g in r['ranges']] == [True, False, False] and [g['previousFinal'] for g in r['ranges']] == [24, 36, 80], '各區間獨立判斷（中期 p0=36、長期 p0=80 的分數遠低於最高 → 不沿用，previousFinal 照記）')
    r, _ = run(BASE_S, BASE_R, prev=prev_of(short=20)); g = short(r)
    check(g['final'] == 20 and g['held'] is False and g['previousFinal'] == 20 and g['computedFinal'] == 20, 'p0 == f：沒有東西可沿用（held False，previousFinal 仍記錄）')

def test_each_reason_not_to_hold():
    # (1) p0 不在區間內
    for p0 in (14, 34, 40, 110):
        r, _ = run(BASE_S, BASE_R, prev=prev_of(short=p0)); g = short(r)
        check(g['final'] == 20 and not g['held'] and g['previousFinal'] == p0, f'p0={p0} 不在短期 15–33 → 不沿用，previousFinal 照記')
    # (2) p0 結構分 < 最高 − gap（f 與 p0 差 <5、p0 反手夠好，只有這一條不成立）：20(60，反手 .10 被 5pp 擋掉)、24(46)、p0=30(44 < 45)
    S2 = {20: 60., 24: 46., 30: 44.}; R2 = {20: .10, 24: .50, 30: .50}
    r, _ = run(S2, R2); check(short(r)['final'] == 24 and 30 not in cp(short(r)), '情境確認：f=24（20 被 5pp 擋掉）、30 的分數 44 < 45 不是候選')
    r, _ = run(S2, R2, prev=prev_of(short=30)); g = short(r)
    check(g['final'] == 24 and not g['held'] and 30 not in cp(g), f"p0=30 分數 44 < 最高 60 − 15：其他條件都過（差 2.0、反手 .50）也不沿用")
    r, _ = run({20: 60., 24: 46., 30: 45.}, R2, prev=prev_of(short=30)); g = short(r)
    check(g['final'] == 30 and g['held'] and g['computedFinal'] == 24, '邊界：p0 分數正好 = 最高 − gap（45.0）→ 仍算候選等級，沿用')
    # (3) p0 反手報酬落後最佳 > 5pp（其他條件都過）
    r, _ = run(BASE_S, {20: .50, 24: .30, 30: .40}, prev=prev_of(short=24)); g = short(r)
    check(g['final'] == 20 and not g['held'], 'p0=24 反手 .30 < .50 − .05 → 不沿用')
    r, _ = run(BASE_S, {20: .50, 24: .45, 30: .40}, prev=prev_of(short=24)); g = short(r)
    check(g['final'] == 24 and g['held'], 'p0 反手剛好 = 最佳 − 5pp（.45）→ 沿用（≥）')
    r, _ = run(BASE_S, {20: .50, 24: .449, 30: .40}, prev=prev_of(short=24)); check(short(r)['final'] == 20 and not short(r)['held'], 'p0 反手 .449 < .45 → 不沿用')
    # (4) f 的結構分 − p0 的結構分 ≥ HYST_POINTS
    for gap_pts, expect in ((4.9, True), (5.0, False), (6.0, False)):
        r, _ = run({20: 60., 24: 60. - gap_pts}, {20: .5, 24: .5}, prev=prev_of(short=24)); g = short(r)
        check(g['held'] is expect and g['final'] == (24 if expect else 20), f'結構分差 {gap_pts}（門檻 {rec.HYST_POINTS}，嚴格小於才沿用）→ held={expect}')
    check(rec.HYST_POINTS == 5.0, 'HYST_POINTS 是具名常數 5.0')

def test_signature_mismatch():
    r, _ = run(BASE_S, BASE_R, prev=prev_of(short=24)); check(short(r)['held'], '基準：簽章相同 → 沿用')
    for k, v in (('scoring', 'pooled+whole'), ('referencePool', 'TW'), ('adjusted', True), ('costPct', 0.585), ('kind', 'EMA')):
        r, _ = run(BASE_S, BASE_R, prev=prev_of(short=24, **{k: v})); g = short(r)
        check(g['final'] == 20 and not g['held'] and g['previousFinal'] == 24 and g['computedFinal'] == 20, f'簽章 {k} 不同（{v!r}）→ 不沿用（第一次換方法就不會被舊選擇綁住），previousFinal 仍記錄')
    for k in SIG:
        r, _ = run(BASE_S, BASE_R, prev=prev_of(short=24, **{k: None})); check(not short(r)['held'], f'舊檔沒有 {k}（例如 VERSION 2 的檔案）→ 不沿用')
    r, _ = run(BASE_S, BASE_R, prev={**prev_of(short=24), 'market': 'TW', 'version': 2}); check(short(r)['held'], '簽章只看 scoring／referencePool／adjusted／costPct／kind（version、market 不影響）')
    r, _ = run(BASE_S, BASE_R, prev=prev_of(short=24, referencePool='TW'), ref_pool='TW'); check(short(r)['held'] and r['referencePool'] == 'TW', 'recommend(ref_pool="TW") 的簽章與舊檔的 TW 一致 → 沿用')
    r, _ = run(BASE_S, BASE_R, prev=prev_of(short=24, costPct=0.585), ticker='2330.TW'); check(short(r)['held'] and r['costPct'] == 0.585 and r['market'] == 'TW', '台股代號：costPct 0.585，與舊檔一致 → 沿用')

def test_p0_not_in_candidates_is_appended():
    # 21 分數 59（與 20 差 1，被間距擋掉）→ 不是候選；沿用它時要補進 candidates，並帶自己的分數與回測
    r, calls = run({20: 60., 21: 59., 24: 58., 30: 52.}, {20: .50, 21: .50, 24: .50, 30: .40}); check(cp(short(r)) == [20, 24, 30] and short(r)['final'] == 20, f'情境確認：候選 {cp(short(r))}，21 不在裡面')
    r, calls = run({20: 60., 21: 59., 24: 58., 30: 52.}, {20: .50, 21: .50, 24: .50, 30: .40}, prev=prev_of(short=21)); g = short(r); c21 = [c for c in g['candidates'] if c['period'] == 21]
    check(g['final'] == 21 and g['held'] and g['computedFinal'] == 20 and cp(g) == [20, 24, 30, 21] and len(c21) == 1, f"p0=21 不在候選：沿用並補進 candidates 尾端 {cp(g)}")
    check(c21[0]['score'] == 59.0 and c21[0]['sarReturn'] == .5 and c21[0]['sarTrades'] == 10 and c21[0]['sarDrawdown'] == -0.1 and c21[0]['sarWinRate'] == .5, f"補進去的候選有自己的分數與回測：{c21[0]}")
    check(21 in calls, '補算了 21 的回測（sar_stats 呼叫過 21）')
    r, calls = run({20: 60., 21: 59., 24: 58., 30: 52.}, {20: .50, 21: .30, 24: .50, 30: .40}, prev=prev_of(short=21)); g = short(r)
    check(g['final'] == 20 and not g['held'] and cp(g) == [20, 24, 30], '不在候選、反手落後 > 5pp → 不沿用，也不補進 candidates')
    r, calls = run(BASE_S, BASE_R, prev=prev_of(short=24)); check(calls.count(24) == 1, 'p0 已在候選時不重算回測（沿用既有的統計）')
    r, calls = run(BASE_S, BASE_R, prev=prev_of(short=14)); check(14 not in calls, '區間外的 p0（14）不會被回測')
    r, calls = run({20: 60., 21: 59., 24: 58., 30: 52.}, {20: .5, 21: .5, 24: .5, 30: .4}, prev=prev_of(short=21, scoring='x')); check(21 not in calls, '簽章不同時不做多餘的回測')
    json.dumps(r, allow_nan=False)
    # 中期、長期同樣適用
    r, _ = run({36: 60., 39: 58.}, {36: .5, 39: .5}, prev=prev_of(medium=39)); g = r['ranges'][1]; check(g['key'] == 'medium' and g['final'] == 39 and g['held'] and g['computedFinal'] == 36, '中期也會沿用')
    r, _ = run({80: 60., 84: 58.}, {80: .5, 84: .5}, prev=prev_of(long=84)); g = r['ranges'][2]; check(g['key'] == 'long' and g['final'] == 84 and g['held'] and g['computedFinal'] == 80, '長期也會沿用')

def test_hold_pure_function():
    mk = lambda p, s, r: {'均線': p, '結構分': s, '反手報酬': r}; cands = [mk(20, 60., .5), mk(24, 58., .5)]; stats0 = lambda p: mk(p, 0., 0.)
    check(rec._hold(20, 24, 15, 33, cands, 58., 60., stats0) == (True, cands[1]), '_hold：全部成立 → (True, p0 的候選)')
    check(rec._hold(20, None, 15, 33, cands, 58., 60., stats0) == (False, None), '_hold：沒有 p0 → False')
    check(rec._hold(20, 24, 25, 33, cands, 58., 60., stats0)[0] is False, '_hold：p0 不在 [lo, hi] → False')

def test_unsuitable():
    r, _ = run(BASE_S, {20: -.10, 24: -.05, 30: -.20}); g = short(r)
    check(g['unsuitable'] is True and g['final'] == 20, f"短期候選報酬都 ≤ 0 → unsuitable True（不改選擇：final 仍是規則 B 的 {g['final']}）")
    r, _ = run(BASE_S, {20: 0., 24: 0., 30: 0.}); check(short(r)['unsuitable'] is True, '最高報酬剛好 0 → unsuitable（≤ 0）')
    r, _ = run(BASE_S, {20: -.10, 24: .0001, 30: -.20}); check(short(r)['unsuitable'] is False, '只要有一個候選 > 0 → 不是 unsuitable')
    r, _ = run({20: 60., 36: 60., 80: 60.}, {20: -.1, 36: .2, 80: -.3}); check([g['unsuitable'] for g in r['ranges']] == [True, False, True], '每個區間各自判斷')
    # 選擇不受旗標影響：同樣的分數與「相對」報酬，整體平移到全負 → final 不變（規則 B 只看相對差）
    pos, _ = run(BASE_S, {20: .50, 24: .46, 30: .30}); neg, _ = run(BASE_S, {20: -.50, 24: -.54, 30: -.70}); check(short(pos)['final'] == short(neg)['final'] and not short(pos)['unsuitable'] and short(neg)['unsuitable'], '報酬整體平移成全負：final 不變、unsuitable 變 True')
    # 沿用舊 final 時，旗標看最後的 candidates（含補進去的 p0）
    r, _ = run({20: 60., 21: 59., 24: 58., 30: 52.}, {20: -.1, 21: -.1, 24: -.1, 30: -.2}, prev=prev_of(short=21)); check(short(r)['held'] and short(r)['unsuitable'] is True, '沿用且全部 ≤ 0 → held 與 unsuitable 可同時成立')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_') and callable(v): print('#', k); v()
    print('ALL PASS')
