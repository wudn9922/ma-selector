"""core/rawstats.py（原始機率／比率／頻率顯示）的測試。用法：python tests/test_rawstats.py"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, metrics, rawstats as rs
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

def test_formatting():
    check(rs.fmt_rate(.625, 8) == '62.5% (n=8)', '62.5% (n=8)')
    check(rs.fmt_rate(0., 4) == '0.0% (n=4)', 'n>0 且真的 0% → 顯示 0.0%（不是破折號）')
    for rate, n in ((0., 0), (np.nan, 0), (np.nan, 5), (.5, 0), (.5, np.nan), (None, 3)): check(rs.fmt_rate(rate, n) == '— (n=0)', f'分母 0／NaN（rate={rate}, n={n}）→ — (n=0)，不顯示 0%')
    check(rs.fmt_freq(1.5) == '1.50' and rs.fmt_freq(np.nan) == '—' and rs.fmt_freq(36.04, 1) == '36.0', '頻率格式')
    check(rs.wick_ratio(2, 9) == (2 / 11, 11) and np.isnan(rs.wick_ratio(0, 0)[0]) and rs.wick_ratio(0, 0)[1] == 0 and rs.wick_ratio(3, 0) == (1.0, 3), '假突破比例＝wick／(wick＋突破)；分母 0 → n=0')
    check(rs.wick_ratio(2, 9)[0] > 0, '假突破比例為正向數值（score.py 的 feature 是取負號後的）')

def test_row_matches_metrics():
    for seed in (5, 9):
        df = data.normalize(synth(seed)); M = metrics.compute_metrics(df).set_index('period'); C = df.close.to_numpy(float); atr = data.wilder_atr(df)
        for p in (15, 22, 33, 45, 60, 110):
            m = M.loc[p]; ma = df.close.rolling(p).mean().to_numpy(); cc = rs.cross_counts(C, ma, atr)
            for y, _ in rs.YEARS:                                                      # 分母重算後，比率與 metrics 的 quickfail 完全相同
                xw, q = cc[y]; assert (q / xw if xw else 0.) == m[f'quickfail_{y}'], (seed, p, y)
            r = rs.raw_row(m, cc)
            exp = lambda rate, n: '— (n=0)' if not n else f'{rate * 100:.1f}% (n={int(n)})'
            assert r['突破成功率'] == exp(m['A_raw@252'], m['A_raw_n@252']) and r['二日成功率'] == exp(m['A_d2@252'], m['A_d2_n@252']) and r['回測成功率'] == exp(m['A_rt@252'], m['A_rt_n@252'])
            assert r['假突破次數'] == int(m['A_wick@252']) and r['突破次數(已判定)'] == int(m['A_raw_n@252'])
            assert r['糾結次數/年(1y/2y/3y)'] == ' / '.join(f"{m[f'tg4_{y}']:.2f}" for y, _ in rs.YEARS) and r['穿插日/年(1y/2y/3y)'] == ' / '.join(f"{m[f'qday_{y}']:.1f}" for y, _ in rs.YEARS)
            assert r['快敗率(1y/2y/3y)'] == ' / '.join(exp(m[f'quickfail_{y}'], cc[y][0]) for y, _ in rs.YEARS)
    check(True, '原始欄位（A_raw／A_d2／A_rt／A_wick／tg4／qday／quickfail）顯示值與 metrics 欄位逐項一致（2 檔 × 6 條均線）')

def test_zero_denominators():
    m = pd.Series({'A_raw@252': np.nan, 'A_raw_n@252': 0, 'A_d2@252': np.nan, 'A_d2_n@252': 0, 'A_rt@252': np.nan, 'A_rt_n@252': 0, 'A_wick@252': 0,
                   'tg4_1y': 0., 'tg4_2y': 0., 'tg4_3y': 0., 'qday_1y': 0., 'qday_2y': 0., 'qday_3y': 0., 'quickfail_1y': 0., 'quickfail_2y': 0., 'quickfail_3y': 0.})
    r = rs.raw_row(m, {'1y': (0, 0), '2y': (0, 0), '3y': (0, 0)})
    check(all(r[k] == '— (n=0)' for k in ('突破成功率', '二日成功率', '回測成功率', '假突破比例')), '沒有任何事件：成功率與假突破比例都是「— (n=0)」')
    check(r['快敗率(1y/2y/3y)'] == '— (n=0) / — (n=0) / — (n=0)', '沒有明顯穿越：快敗率顯示「— (n=0)」，不是 0%')
    check(r['糾結次數/年(1y/2y/3y)'] == '0.00 / 0.00 / 0.00', '糾結次數/年＝0.00（頻率，真的是 0 次）')

def test_read_only():
    df = data.normalize(synth(7)); M = metrics.compute_metrics(df); before = M.copy(); rs.raw_row(M.set_index('period').loc[25])
    check(M.equals(before), 'raw_row 不修改 metrics 表')

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f): print('#', n); f()
    print('ALL PASS')
