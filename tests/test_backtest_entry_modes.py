"""回測進場價模式 entry_mode 的測試（合成資料）。
1) gap_open（預設）與改動前的 core/backtest.py（OLD_COMMIT）逐位元組相同：多組隨機股價 × simple／complex × longonly × retest × 不同上下緣／成本／早退設定
2) fixed_band：造出 U=101、開盤 103 的跳空 → gap_open 成交 103、fixed_band 成交 101；訊號日相同、只有成交價與損益改變（突破、回測、空單）
3) 開盤在邊界之下／剛好在邊界：兩種模式完全相同
4) 非法 entry_mode → ValueError
用法：python tests/test_backtest_entry_modes.py"""
import subprocess, sys, types
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import backtest as bt, data
OLD_COMMIT = 'a150cfb20d90b0355a4ce0f5116594072fd0e92a'          # 加入 entry_mode 之前的 main
def old_module():
    src = subprocess.run(['git', 'show', f'{OLD_COMMIT}:core/backtest.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    m = types.ModuleType('core._backtest_old'); m.__package__ = 'core'; exec(compile(src, 'core/backtest.py@old', 'exec'), m.__dict__); return m
OLD = old_module()
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
def same(a, b):
    sa, ta, ea = a; sb, tb, eb = b
    return sa.keys() == sb.keys() and all((sa[k] == sb[k]) or (isinstance(sa[k], float) and np.isnan(sa[k]) and np.isnan(sb[k])) for k in sa) and ta == tb and np.array_equal(ea, eb)

def arrays(seed, n=1000):
    df = data.normalize(synth(seed, n)); return [df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close', 'volume')], data.wilder_atr(df), df

def test_default_unchanged():
    n = 0; trades = 0
    for seed in (3, 11, 29, 41, 57):
        (O, H, L, C, V), atr, df = arrays(seed)
        for p in (15, 22, 33, 60):
            ma = df.close.rolling(p).mean().to_numpy()
            for mode in ('simple', 'complex'):
                for longonly in (True, False):
                    for retest in (True, False):
                        for kw in (dict(), dict(x=.012, c=.02, cost=.002), dict(x=.0, c=.0), dict(x=.05, c=.05, tp=.05), dict(ex_vol=True, ex_close=False, ex_day2=False), dict(lo=300)):
                            args = dict(mode=mode, longonly=longonly, retest=retest, return_eq=True, **{'lo': 504, **kw})
                            o = OLD.run(O, H, L, C, V, ma, atr, **args); a = bt.run(O, H, L, C, V, ma, atr, **args); b = bt.run(O, H, L, C, V, ma, atr, entry_mode='gap_open', **args)
                            assert same(o, a) and same(o, b), (seed, p, mode, longonly, retest, kw); n += 1; trades += len(o[1])
    check(True, f'預設與 gap_open 對改動前 backtest 完全相同（{n} 組設定、{trades} 筆交易；stats、trades、equity 逐位元組相同）')
    check(trades > 200, f'測試涵蓋足夠交易（{trades} 筆）')

def flat(n, ma=100.):
    """ma 固定 100、atr 固定 1；所有 K 線預設在 MA 之上遠處（不觸發任何事件）"""
    O = np.full(n, 105.); H = np.full(n, 106.); L = np.full(n, 104.); C = np.full(n, 105.); V = np.full(n, 1e6); return O, H, L, C, V, np.full(n, ma), np.ones(n)
def setbar(A, t, o, h, l, c): A[0][t], A[1][t], A[2][t], A[3][t] = o, h, l, c

def long_breakout_case(open_t=103., n=30):
    """前面收在均線下方（side=−1）；t=10 開盤 open_t、最高 ≥ 上緣 U=101（x=.01）→ 多單突破進場；t=20 往下碰下緣 98.5 出場（簡單策略）"""
    O, H, L, C, V, ma, atr = flat(n)
    for t in range(0, 10): setbar((O, H, L, C), t, 98., 98.5, 97.5, 98.)
    setbar((O, H, L, C), 10, open_t, max(open_t, 104.), min(open_t, 102.5) if open_t >= 101 else 100.5, 103.5)
    setbar((O, H, L, C), 20, 99., 99., 97., 98.)
    for t in range(21, n): setbar((O, H, L, C), t, 98., 98.5, 97.5, 98.)               # 出場後留在均線下方，不再有新訊號
    return O, H, L, C, V, ma, atr
def run_both(case, **kw):
    O, H, L, C, V, ma, atr = case; r = {}
    for m in ('gap_open', 'fixed_band'): r[m] = bt.run(O, H, L, C, V, ma, atr, lo=0, mode='simple', entry_mode=m, **kw)
    return r

def test_breakout_gap():
    r = run_both(long_breakout_case(103.))
    tg, tf = r['gap_open'][1], r['fixed_band'][1]
    check(len(tg) == len(tf) == 1 and (tg[0]['tin'], tg[0]['tout'], tg[0]['side'], tg[0]['kind']) == (tf[0]['tin'], tf[0]['tout'], tf[0]['side'], tf[0]['kind']) == (10, 20, 1, 'B'), f'突破：訊號日／出場日／方向／類型相同 {tg[0]["tin"]}→{tg[0]["tout"]}')
    exit_px = 98.5                                                                    # min(開盤 99, 下緣 98.5)
    check(abs(tg[0]['ret'] - ((exit_px / 103. - 1) - .001)) < 1e-12, f'gap_open 成交價 103（損益 {tg[0]["ret"]:.6f}）')
    check(abs(tf[0]['ret'] - ((exit_px / 101. - 1) - .001)) < 1e-12, f'fixed_band 成交價 101（損益 {tf[0]["ret"]:.6f}）')
    check(tf[0]['ret'] > tg[0]['ret'] and abs(r['fixed_band'][0]['總報酬'] - tf[0]['ret']) < 1e-12 and abs(r['gap_open'][0]['總報酬'] - tg[0]['ret']) < 1e-12, '損益依成交價不同而改變，總報酬一致')

def test_no_gap_same():
    for o in (100.5, 101.0):                                  # 開盤在上緣之下／剛好在上緣：兩種模式都以上緣 101 成交
        r = run_both(long_breakout_case(o)); a, b = r['gap_open'][1][0], r['fixed_band'][1][0]
        check(a == b and abs(a['ret'] - ((98.5 / 101. - 1) - .001)) < 1e-12, f'開盤 {o}（≤ 上緣 101）：兩種模式相同，成交價 101')
    check(same(*[run_both(long_breakout_case(101.))[m] + (np.zeros(1),) for m in ('gap_open', 'fixed_band')]), '開盤＝上緣：stats／trades 相同')

def retest_case(n=30):
    """側＝多（連續收在 MA 上）→ t=10 回測均線（低點 ≤ MA+0.1ATR 且收盤 ≥ MA−0.1ATR）→ t=11 反彈 K 線 → t=12 開盤 103 跳空越過上緣 101 → 回測進場；t=20 碰下緣出場"""
    O, H, L, C, V, ma, atr = flat(n); A = (O, H, L, C)
    for t in range(0, 10): setbar(A, t, 102., 102.5, 101.5, 102.)
    setbar(A, 10, 101., 102., 100., 100.5); setbar(A, 11, 100.6, 100.9, 100.5, 100.8)         # 反彈 K 線（收紅、收盤>前日、最高 <U 以免當天就進場）
    setbar(A, 12, 103., 104., 102.5, 103.5); setbar(A, 20, 99., 99., 97., 98.)
    for t in range(21, n): setbar(A, t, 98., 98.5, 97.5, 98.)
    return O, H, L, C, V, ma, atr
def test_retest_gap():
    r = run_both(retest_case()); tg, tf = r['gap_open'][1], r['fixed_band'][1]
    check(len(tg) == len(tf) == 1 and tg[0]['kind'] == tf[0]['kind'] == 'R' and (tg[0]['tin'], tg[0]['tout']) == (tf[0]['tin'], tf[0]['tout']) == (12, 20), f'回測進場路徑：訊號日相同、類型 R（tin={tg[0]["tin"]}）')
    check(abs(tg[0]['ret'] - ((98.5 / 103. - 1) - .001)) < 1e-12 and abs(tf[0]['ret'] - ((98.5 / 101. - 1) - .001)) < 1e-12, '回測：gap_open 成交 103、fixed_band 成交 101')
    off = bt.run(*retest_case(), lo=0, mode='simple', retest=False)[1]
    check(off == [], '關掉回測進場時此情境沒有交易（確認進場確實來自回測路徑）')

def test_complex_and_short():
    for mode in ('simple', 'complex'):
        O, H, L, C, V, ma, atr = long_breakout_case(103.)
        a = bt.run(O, H, L, C, V, ma, atr, lo=0, mode=mode, entry_mode='gap_open')[1][0]; b = bt.run(O, H, L, C, V, ma, atr, lo=0, mode=mode, entry_mode='fixed_band')[1][0]
        check((a['tin'], a['kind']) == (b['tin'], b['kind']) and a['ret'] != b['ret'], f'{mode}：進場日相同、損益依成交價改變（{a["ret"]:.5f} vs {b["ret"]:.5f}）')
    # 空單（longonly=False）：前面在 MA 上方；t=10 開盤 97 跳空越過下緣 98.5 → gap_open 成交 97、fixed_band 成交 98.5；t=20 碰上緣 101 出場（max(開盤102, 101)=102）
    n = 30; O, H, L, C, V, ma, atr = flat(n); A = (O, H, L, C)
    for t in range(0, 10): setbar(A, t, 102., 102.5, 101.5, 102.)
    setbar(A, 10, 97., 98., 96., 96.5)
    for t in range(11, n): setbar(A, t, 96.5, 97.5, 96., 96.5)                              # 持空期間留在均線下方（不碰上緣 101）
    setbar(A, 20, 102., 103., 101.5, 102.5)
    for m, e in (('gap_open', 97.), ('fixed_band', 98.5)):
        tr = bt.run(O, H, L, C, V, ma, atr, lo=0, mode='simple', longonly=False, entry_mode=m)[1][0]
        check((tr['tin'], tr['tout'], tr['side']) == (10, 20, -1) and abs(tr['ret'] - (-(102. / e - 1) - .001)) < 1e-12, f'空單 {m}：成交價 {e}、訊號日相同')

def test_property_simple_signals_identical():
    """simple 策略的訊號與出場不依賴成交價 → 隨機資料上 fixed_band 與 gap_open 的 (tin, tout, side, kind) 完全相同；損益只在「進場日開盤越過邊界」時不同"""
    ndiff = ntrades = 0
    for seed in (3, 11, 29, 41):
        (O, H, L, C, V), atr, df = arrays(seed)
        for p in (15, 25, 60):
            ma = df.close.rolling(p).mean().to_numpy(); mp = np.r_[np.nan, ma[:-1]]
            for lo_ in (0, 500):
                a = bt.run(O, H, L, C, V, ma, atr, lo=lo_, mode='simple', longonly=False, entry_mode='gap_open')[1]; b = bt.run(O, H, L, C, V, ma, atr, lo=lo_, mode='simple', longonly=False, entry_mode='fixed_band')[1]
                assert [(t['tin'], t['tout'], t['side'], t['kind']) for t in a] == [(t['tin'], t['tout'], t['side'], t['kind']) for t in b], (seed, p)
                for x, y in zip(a, b):
                    ntrades += 1; t = x['tin']; band = mp[t] * 1.01 if x['side'] == 1 else mp[t] * .985
                    crossed = (O[t] > band) if x['side'] == 1 else (O[t] < band)
                    if not crossed: assert x['ret'] == y['ret'], (seed, p, t)
                    else: ndiff += 1
    check(True, f'simple 隨機資料：{ntrades} 筆交易訊號完全相同；其中 {ndiff} 筆因開盤跳空越過邊界而成交價不同，其餘損益完全相同')

def test_invalid_mode():
    try: bt.run(*[np.ones(10)] * 5, np.ones(10), np.ones(10), entry_mode='nope'); check(False, 'ValueError')
    except ValueError: check(True, '非法 entry_mode → ValueError')
    check(bt.ENTRY_MODES == ('gap_open', 'fixed_band'), f'合法值 {bt.ENTRY_MODES}')

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f): print('#', n); f()
    print('ALL PASS')
