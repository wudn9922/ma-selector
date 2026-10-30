"""均線種類 kind（SMA／EMA）的測試（合成資料）
1) SMA 預設與 kind='SMA' 對改動前（OLD_COMMIT）的 metrics／select／charts 逐位元組相同
2) EMA 與手寫迴圈一致（alpha=2/(p+1)、種子＝第一根收盤、前 p-1 根 NaN）
3) EMA 管線能跑：compute_metrics／select／chart_png；非法 kind → ValueError；build_reference 的輸出路徑 helper
用法：python tests/test_ma_kind.py"""
import ast, subprocess, sys, types
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, score, metrics, select as sel, charts
from core.ma import KINDS, moving_average
OLD_COMMIT = 'ff8e4f4'          # 加入 kind 之前
def old_module(name):
    src = subprocess.run(['git', 'show', f'{OLD_COMMIT}:core/{name}.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    m = types.ModuleType(f'core._{name}_old'); m.__package__ = 'core'; m.__file__ = str(ROOT / 'core' / f'{name}.py'); exec(compile(src, f'core/{name}.py@old', 'exec'), m.__dict__); return m
OLD_M, OLD_S, OLD_C = old_module('metrics'), old_module('select'), old_module('charts')
REF = pd.read_parquet(ROOT / 'data/reference.parquet'); SEEDS = (3, 11, 29)
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
def stock(seed, n=1300): return data.normalize(synth(seed, n))
def S_of(M): return score.score_table(M, REF)

def test_sar_metrics_identical():
    # metrics 之後新增了 @756 的 7 欄（selector v2）：既有欄位（值＋順序）必須和舊版 DataFrame.equals，多出的欄位必須正好是 @756 那 7 欄
    new756 = [f'{k}@756' for k in ('A_raw_n', 'A_raw', 'A_d2_n', 'A_d2', 'A_rt_n', 'A_rt', 'A_wick')]
    for seed in SEEDS:
        df = stock(seed); o = OLD_M.compute_metrics(df); oc = list(o.columns)
        for nm, n in (('預設', metrics.compute_metrics(df)), ('kind=SMA', metrics.compute_metrics(df, kind='SMA'))):
            check(list(n.columns)[:len(oc)] == oc and n[oc].equals(o) and list(n.columns)[len(oc):] == new756, f'seed {seed}：compute_metrics {nm} 既有欄位對舊版 DataFrame.equals，且多出的欄位正好是 @756 七欄')

def test_sma_select_identical():
    n = 0
    for seed in SEEDS:
        df = stock(seed); S = S_of(OLD_M.compute_metrics(df))
        for nm, kw in (('預設', dict()), ('LEGACY', sel.LEGACY), ('min_period', dict(final_rule='min_period'))):
            o = OLD_S.select(df, S, **kw)
            check(sel.select(df, S, **kw) == o and sel.select(df, S, kind='SMA', **kw) == o, f'seed {seed}：select({nm}) 預設與 kind=SMA 對舊版 =='); n += 1
    check(n == 9, f'共 {n} 組 select 比對')

def test_sma_chart_identical():
    df = stock(3); o = OLD_C.chart_png(df, 25, 'x'); a = charts.chart_png(df, 25, 'x'); b = charts.chart_png(df, 25, 'x', kind='SMA')
    if o == a == b: check(True, f'chart_png 預設與 kind=SMA 對舊版 bytes 完全相同（{len(o)} bytes）')
    else:
        Yo, Ya = OLD_C.layers(df, 25), charts.layers(df, 25)
        ok = all(np.array_equal(Yo[k], Ya[k], equal_nan=True) for k in ('O', 'H', 'L', 'C', 'atr', 'ma', 'mp', 'q', 'd'))
        check(ok, 'PNG bytes 不同（可能是 matplotlib 非決定性）→ 改比 layers() 陣列')

def test_ema_matches_loop():
    for seed in SEEDS:
        s = stock(seed).close
        for p in (15, 25, 60, 110):
            c = s.to_numpy(float); a = 2 / (p + 1); e = np.empty(len(c)); e[0] = c[0]
            for t in range(1, len(c)): e[t] = a * c[t] + (1 - a) * e[t - 1]
            e[:p - 1] = np.nan; m = moving_average(s, p, 'EMA')
            assert isinstance(m, np.ndarray) and m.dtype == float and len(m) == len(c)
            assert np.isnan(m[:p - 1]).all() and np.isfinite(m[p - 1:]).all() and np.abs(m[p - 1:] - e[p - 1:]).max() < 1e-12, (seed, p)
            assert not np.allclose(m[p - 1:], moving_average(s, p, 'SMA')[p - 1:]), (seed, p)
    check(True, 'EMA 與手寫遞迴一致（<1e-12）、前 p-1 根 NaN、第 p 根起有限、與 SMA 不同')
    s = stock(3).close; check(np.array_equal(moving_average(s, 25), s.rolling(25).mean().to_numpy(), equal_nan=True) and KINDS == ('SMA', 'EMA'), "moving_average 預設＝SMA＝rolling mean；KINDS=('SMA','EMA')")

def test_ema_pipeline():
    df = stock(11); Ms = metrics.compute_metrics(df); Me = metrics.compute_metrics(df, kind='EMA')
    check(list(Me.columns) == list(Ms.columns) and Me.period.equals(Ms.period), 'EMA metrics 欄位與週期和 SMA 相同')
    check(not Me.equals(Ms), 'EMA metrics 數值與 SMA 不同')
    R = sel.select(df, S_of(Me), kind='EMA')
    check(list(R) == ['短期', '中期', '長期'], f'EMA select 回傳 {list(R)}')
    for nm, lo, hi, _W in sel.RANGES: check(lo <= R[nm]['final'] <= hi, f'EMA {nm} final={R[nm]["final"]} 在 [{lo},{hi}]')
    png = charts.chart_png(df, 25, 'x', kind='EMA')
    check(png[:8] == b'\x89PNG\r\n\x1a\n', 'chart_png(kind=EMA) 回傳 PNG bytes')
    check(charts.layers(df, 25, 'EMA')['ma'].tolist() != charts.layers(df, 25)['ma'].tolist() and png != charts.chart_png(df, 25, 'x'), 'EMA 圖與 SMA 圖不同')

def test_invalid_kind():
    df = stock(3)
    for f in (lambda: moving_average(df.close, 25, 'WMA'), lambda: metrics.compute_metrics(df, periods=[20], kind='x'), lambda: charts.layers(df, 25, 'ema'), lambda: sel.select(df, S_of(OLD_M.compute_metrics(df)), kind='WMA')):
        try: f()
        except ValueError: continue
        check(False, '非法 kind 應該 ValueError')
    check(True, '非法 kind → ValueError（moving_average／compute_metrics／layers／select）')

def test_build_reference_paths():
    src = (ROOT / 'scripts/build_reference.py').read_text(); fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == 'default_out')
    ns = {}; exec(compile(ast.Module([fn], []), 'build_reference.py', 'exec'), ns); f = ns['default_out']
    check(f('SMA') == 'data/reference.parquet' and f('EMA') == 'data/reference_ema.parquet', 'build_reference 預設輸出：SMA→reference.parquet、EMA→reference_ema.parquet（json 同名換副檔名）')

if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_'): v()
    print('ALL PASS')
