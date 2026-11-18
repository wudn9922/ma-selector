"""市場設定（core/market.py）與成本參數（events／sar_stats／select／select_v2 的 cost=）的測試
1) market_of／COSTS／基準檔路徑（含台股檔存在與不存在，用暫存檔）
2) 預設成本與改動前（BASE_COMMIT 的 core/events.py、core/select.py）逐位元組相同：events、sar_stats、select（含 LEGACY）；明確傳預設值也相同
3) 成本只影響交易報酬：事件／持倉紀錄不變，每筆報酬差正好 Δcost；反手報酬少約 筆數×Δcost；候選、分數不變；metrics／特徵（＝基準檔內容）與成本無關
用法：python tests/test_market_cost.py（用封存的 bars：experiments/rescue_validation/raw_outputs/<TICKER>/bars.csv，不連網）"""
import subprocess, sys, tempfile, types
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from core import data, events as ev, market, metrics, score, select as sel, select_v2, backtest as bt
from core.data import wilder_atr
from core.ma import moving_average
import build_reference as br, build_reference_v2 as b2
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

BASE_COMMIT = '1507391'          # 加入 cost 參數之前的 HEAD
RAW = ROOT / 'experiments' / 'rescue_validation' / 'raw_outputs'; TICKERS = ('ADM', 'ADSK', 'AES')
REF = pd.read_parquet(ROOT / 'data' / 'reference.parquet')
def old_module(name, **inject):
    src = subprocess.run(['git', 'show', f'{BASE_COMMIT}:core/{name}.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    m = types.ModuleType(f'core._{name}_base'); m.__package__ = 'core'; m.__file__ = str(ROOT / 'core' / f'{name}.py'); exec(compile(src, f'core/{name}.py@{BASE_COMMIT}', 'exec'), m.__dict__)
    for k, v in inject.items(): setattr(m, k, v)
    return m
OLD_EV = old_module('events'); OLD_SEL = old_module('select', ev=OLD_EV, bt=old_module('backtest'))       # 舊 select 也改用舊 events（完全是改動前的程式）
_D = {}
def bars(tk):
    if tk not in _D:
        df = data.load(RAW / tk / 'bars.csv'); M = metrics.compute_metrics(df); _D[tk] = (df, M, score.score_table(M, REF), score.score_table(M, REF, pct_mode='pooled'))
    return _D[tk]
def arrays(df): return [df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')], wilder_atr(df)
R = repr   # repr 對 float 是精確的（含 nan），拿來比「逐位元組相同」

def test_market_of():
    for tk, m in (('AAPL', 'US'), ('BRK-B', 'US'), ('2330.TW', 'TW'), ('6274.TWO', 'TW'), ('2330.tw', 'TW'), (' 6274.two ', 'TW'), ('0050.TW', 'TW'), ('^TWII', 'US'), ('TW', 'US'), ('XTW', 'US'), ('TWO', 'US'), ('1234.TWX', 'US'), ('7203.T', 'US')):
        check(market.market_of(tk) == m, f'market_of({tk!r}) == {m}')
    check(market.COSTS == {'TW': 0.00585, 'US': 0.001} and market.cost_of('2330.TW') == 0.00585 and market.cost_of('AAPL') == 0.001 and ev.COST == market.COSTS['US'], 'COSTS＝台股 0.585%／美股 0.1%，美股＝events.COST（舊行為）')
    check(abs(0.001425 * 2 + 0.003 - market.COSTS['TW']) < 1e-12, '台股成本＝牌告手續費 0.1425%×2＋賣出證交稅 0.3%')

def test_reference_paths():
    us, tw = market.ref_files('US', ROOT), market.ref_files('TW', ROOT)
    check(us['sma'] == ROOT / 'data/reference.parquet' and us['v2'] == ROOT / 'data/reference_v2.parquet', '美股檔路徑不變')
    check([str(tw[k].relative_to(ROOT)) for k in ('sma', 'v2')] == [br.default_out('SMA', 'tw'), b2.default_out('tw')] == ['data/reference_tw.parquet', 'data/reference_tw_v2.parquet'], '台股檔路徑＝build_reference／build_reference_v2 --market tw 的輸出路徑')
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); (root / 'data').mkdir(); f = market.ref_files('TW', root); u = market.ref_files('US', root)
        check(market.pick_pool('TW', root) == ('US', u['sma'], u['v2'], 'US'), '台股檔都不存在 → 退回美股檔（池 US）')
        f['v2'].touch(); check(market.pick_pool('TW', root) == ('US', u['sma'], f['v2'], 'TW'), '只有台股 v2：SMA 仍退回美股，v2 用台股（各自判斷，v2 池另外回報）')
        f['sma'].touch(); check(market.pick_pool('TW', root) == ('TW', f['sma'], f['v2'], 'TW'), '台股 SMA、v2 都存在 → 都用台股')
        f['v2'].unlink(); check(market.pick_pool('TW', root) == ('TW', f['sma'], u['v2'], 'US'), '只有台股 SMA：v2 退回美股')
        check(market.pick_pool('US', root) == ('US', u['sma'], u['v2'], 'US'), '美股永遠用美股檔（即使台股檔存在）')

def test_default_cost_identical_to_base():
    for tk in TICKERS:
        df, M, S, Sp = bars(tk); (O, H, L, C), atr = arrays(df); N = len(C)
        for p in (15, 24, 33, 60, 110):
            ma = moving_average(df.close, p)
            o = OLD_EV.events(O, H, L, C, ma, atr); n = ev.events(O, H, L, C, ma, atr); e = ev.events(O, H, L, C, ma, atr, cost=ev.COST); e2 = ev.events(O, H, L, C, ma, atr, cost=0.001)
            check(R(o) == R(n) == R(e) == R(e2), f'{tk} SMA{p}：events（預設／明確傳 COST／0.001）與改動前逐位元組相同（{len(o[4])} 筆）')
            for W in (252, 504, 756):
                a = OLD_SEL.sar_stats(O, H, L, C, atr, ma, N - W); b = sel.sar_stats(O, H, L, C, atr, ma, N - W, window_mode='legacy_exit'); c = sel.sar_stats(O, H, L, C, atr, ma, N - W, cost=0.001, window_mode='legacy_exit')
                check(R(a) == R(b) == R(c), f'{tk} SMA{p} 近{W // 252}年：sar_stats 與改動前相同')
        o = OLD_SEL.select(df, S); check(R(o) == R(sel.select(df, S, window_mode='legacy_exit')) == R(sel.select(df, S, cost=0.001, window_mode='legacy_exit')) == R(sel.select(df, S, cost=ev.COST, window_mode='legacy_exit')), f'{tk}：select（預設／明確 0.001）與改動前逐位元組相同，final＝{[o[k]["final"] for k in o]}')
        o = OLD_SEL.select(df, Sp, **{k: v for k, v in sel.LEGACY.items() if k != 'window_mode'}); check(R(o) == R(sel.select(df, Sp, **sel.LEGACY)) == R(sel.select(df, Sp, cost=0.001, **sel.LEGACY)), f'{tk}：LEGACY（pooled、whole、只做多）與改動前相同')
    # bt.run 預設 cost 本來就是 .001
    df, M, S, Sp = bars('ADM'); (O, H, L, C), atr = arrays(df); ma = moving_average(df.close, 24); V = df.volume.to_numpy(float)
    check(R(bt.run(O, H, L, C, V, ma, atr, lo=len(C) - 252)) == R(bt.run(O, H, L, C, V, ma, atr, lo=len(C) - 252, cost=.001)), 'bt.run 預設 cost＝.001')

def test_cost_only_changes_trade_returns():
    dc = market.COSTS['TW'] - market.COSTS['US']
    for tk in TICKERS:
        df, M, S, Sp = bars(tk); (O, H, L, C), atr = arrays(df); N = len(C)
        for p in (15, 20, 33, 60):
            ma = moving_average(df.close, p); lo_ = ev.events(O, H, L, C, ma, atr); hi = ev.events(O, H, L, C, ma, atr, cost=market.COSTS['TW'])
            check(R(lo_[:4]) == R(hi[:4]), f'{tk} SMA{p}：突破／假突破／回測事件與持倉紀錄（plog）與成本無關')
            check(len(lo_[4]) == len(hi[4]) and all(a[:3] == b[:3] and a[4] == b[4] and abs((a[3] - b[3]) - dc) < 1e-12 for a, b in zip(lo_[4], hi[4])), f'{tk} SMA{p}：{len(lo_[4])} 筆交易，每筆報酬差正好 Δcost＝{dc:.5f}')
            s1 = sel.sar_stats(O, H, L, C, atr, ma, N - 504); s2 = sel.sar_stats(O, H, L, C, atr, ma, N - 504, cost=market.COSTS['TW']); n = s1['筆數']
            drop = float(np.log((1 + s1['報酬']) / (1 + s2['報酬'])))
            check(s2['筆數'] == n and s2['報酬'] < s1['報酬'] and abs(drop - n * dc) <= 0.05 * n * dc, f'{tk} SMA{p} 近2年：{n} 筆、報酬 {s1["報酬"]:+.3f} → {s2["報酬"]:+.3f}；log 報酬少 {drop:.4f} ≈ 筆數×Δcost＝{n * dc:.4f}')
        a = sel.select(df, S); b = sel.select(df, S, cost=market.COSTS['TW'])
        for nm in a:
            ca, cb = a[nm]['cands'], b[nm]['cands']
            check([(c['均線'], c['分數'], c['結構分']) for c in ca] == [(c['均線'], c['分數'], c['結構分']) for c in cb] and a[nm]['best'] == b[nm]['best'], f'{tk} {nm}：候選、分數與成本無關')
            check(all(y['反手報酬'] < x['反手報酬'] and y['簡單報酬'] <= x['簡單報酬'] + 1e-12 and y['複雜報酬'] <= x['複雜報酬'] + 1e-12 and x['反手筆數'] == y['反手筆數'] for x, y in zip(ca, cb)), f'{tk} {nm}：成本變高 → 反手／只做多報酬下降、筆數不變')
    # 反手報酬與簡單報酬都是「每筆」成本：顯式 cost=0 時，反手報酬 > 預設
    df, M, S, Sp = bars('ADM'); z = sel.select(df, S, cost=0.0); d = sel.select(df, S)
    check(all(x['反手報酬'] > y['反手報酬'] for nm in z for x, y in zip(z[nm]['cands'], d[nm]['cands'])), 'cost=0 的反手報酬都高於預設 0.1%')

def test_metrics_and_reference_independent_of_cost():
    df, M, S, Sp = bars('AES'); orig = ev.events
    def costly(*a, **k): k['cost'] = 0.05; return orig(*a, **k)       # 強迫 metrics 內部的 events 用 5% 成本
    ev.events = costly
    try: M2 = metrics.compute_metrics(df); M3 = metrics.compute_metrics(df, kind='EMA')
    finally: ev.events = orig
    check(M2.equals(M) and list(M2.columns) == list(M.columns) and all(M2[c].to_numpy().tobytes() == M[c].to_numpy().tobytes() for c in M.columns), 'metrics.compute_metrics 的結果（逐位元組）與 events 用什麼成本無關')
    check(score.make_features(M2).equals(score.make_features(M)) and score.score_table(M2, REF).equals(S) and M3.equals(metrics.compute_metrics(df, kind='EMA')), '特徵（基準檔 reference*.parquet 的內容）、分數、EMA 版 metrics 也與成本無關')
    src = (ROOT / 'core' / 'metrics.py').read_text(); check('cost' not in src.lower() and 'trs' in src and '_trs' in src, 'metrics.py 只取 events 的 brk／wick／rts，丟掉 trades（唯一帶成本的輸出），也沒有成本參數')
    srcb = (ROOT / 'scripts' / 'build_reference.py').read_text() + (ROOT / 'scripts' / 'build_reference_v2.py').read_text(); check('cost' not in srcb.lower() and 'sar_stats' not in srcb and 'select' not in srcb, '建基準檔的腳本只用 metrics／score 特徵，不碰回測成本')

def test_select_v2_cost():
    df, M, S, Sp = bars('ADM'); rv = pd.read_parquet(ROOT / 'data' / 'reference_v2.parquet')
    a = select_v2.select_v2(df, M, rv); b = select_v2.select_v2(df, M, rv, cost=0.001); c = select_v2.select_v2(df, M, rv, cost=market.COSTS['TW'])
    check(R(a) == R(b), 'select_v2 預設成本與明確 0.001 相同')
    ca, cc = a['短期']['cands'], c['短期']['cands']
    check([x['均線'] for x in ca] == [x['均線'] for x in cc] and all(y['反手報酬'] < x['反手報酬'] and y['反手報酬_1y'] < x['反手報酬_1y'] for x, y in zip(ca, cc)), 'select_v2：候選不變、台股成本下反手報酬較低（2y 與 1y 參考欄都是）')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_') and callable(v): print('#', k); v()
    print('ALL PASS')
