"""core/metrics.py 的 tg4_*／qday_* 年化分母測試。用法：python tests/test_metrics_annualization.py
1) 完整歷史（約 1254 棒）：與修正前（HEAD 當時的 core/metrics.py）逐位元組相同。
2) 短歷史（只留最後 450 棒）：分母改為視窗內可評估棒數 eff，而不是名目視窗 W。"""
import importlib.util, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT)]
from core import data, metrics, tangle
from core.ma import moving_average
BASE_COMMIT = 'bcbcdbddf365068777de04c543ee940da7e6130c'      # 修正前的 commit（metrics 仍以名目視窗 W 年化）
RAW = ROOT / 'experiments' / 'rescue_validation' / 'raw_outputs'
YEARS = (('1y', 252), ('2y', 504), ('3y', 756))
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg

def load_orig():
    src = subprocess.run(['git', 'show', f'{BASE_COMMIT}:core/metrics.py'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    path = Path(tempfile.mkdtemp(prefix='metrics_orig_')) / 'metrics_orig.py'; path.write_text(src, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('core._metrics_orig', path); m = importlib.util.module_from_spec(spec); m.__package__ = 'core'
    spec.loader.exec_module(m); return m

def tickers(n): return sorted(p.parent.name for p in RAW.glob('*/bars.csv'))[:n]

def test_full_history_identical():
    orig = load_orig(); ts = tickers(12); assert len(ts) >= 10
    for tk in ts:
        df = data.load(RAW / tk / 'bars.csv'); assert len(df) > 1000, (tk, len(df))
        drop = [c for c in metrics.compute_metrics(df, (20,)).columns if c.startswith('quickfail_')]       # 快敗率定義已改（未成熟穿越不計），其餘欄位仍須逐位元組相同
        pd.testing.assert_frame_equal(metrics.compute_metrics(df).drop(columns=drop), orig.compute_metrics(df).drop(columns=drop), check_exact=True)
    check(True, f'完整歷史 {len(ts)} 檔：compute_metrics（除 quickfail_*）與 {BASE_COMMIT[:7]} 的版本逐位元組相同（assert_frame_equal check_exact）')

def test_short_history_uses_effective_bars():
    orig = load_orig()
    for tk in tickers(3):
        df = data.load(RAW / tk / 'bars.csv').tail(450).reset_index(drop=True); N = len(df)
        O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = data.wilder_atr(df)
        periods = (20, 60, 110); new = metrics.compute_metrics(df, periods).set_index('period'); old = orig.compute_metrics(df, periods).set_index('period')
        check(list(new.columns) == list(old.columns), f'{tk}：欄位名稱與順序不變')
        for p in periods:
            ma = moving_average(df.close, p); mp = np.r_[np.nan, ma[:-1]]
            q = tangle.qualify(O, H, L, C, ma, mp, atr); spans = tangle.detect(O, H, L, C, ma, mp, atr)
            for nm, W in YEARS:
                lo = max(N - W, 0); eff = sum(1 for t in range(lo, N) if t >= 1 and not np.isnan(mp[t]) and not np.isnan(atr[t]))
                assert 1 <= eff <= W and (nm == '1y' or eff < W), (tk, p, nm, eff)      # 450 棒：2y／3y 一定不足，1y 在短週期可能剛好完整（eff==W，此時與舊值相同）
                nq = int(q[lo:].sum()); ntg = sum(1 for _a, e, _h, _l in spans if e >= lo)
                assert new.loc[p, f'qday_{nm}'] == nq * 252 / eff, (tk, p, nm)
                assert new.loc[p, f'tg4_{nm}'] == ntg * 252 / eff, (tk, p, nm)
                assert np.isclose(new.loc[p, f'qday_{nm}'], old.loc[p, f'qday_{nm}'] * W / eff, rtol=1e-12, atol=0) and np.isclose(new.loc[p, f'tg4_{nm}'], old.loc[p, f'tg4_{nm}'] * W / eff, rtol=1e-12, atol=0), (tk, p, nm)
                if nq and eff < W: assert new.loc[p, f'qday_{nm}'] > old.loc[p, f'qday_{nm}']
                if eff == W: assert new.loc[p, f'qday_{nm}'] == old.loc[p, f'qday_{nm}'] and new.loc[p, f'tg4_{nm}'] == old.loc[p, f'tg4_{nm}']
                n_, q_, _p = metrics.quickfail_counts(metrics.clear_crossings(C, ma, atr), lo, N)
                assert new.loc[p, f'quickfail_{nm}'] == (q_ / n_ if n_ else 0.)                  # quickfail 用成熟穿越定義（見下方 test_quickfail_*）
            ev = [c for c in new.columns if c.startswith('A_')]
            pd.testing.assert_frame_equal(new.loc[[p], ev], old.loc[[p], ev], check_exact=True)  # 事件成功率不變
        assert not new.filter(regex='^(tg4|qday)_').isna().any().any()
        check(True, f'{tk}（最後 450 棒；period 20／60／110；1y／2y／3y）：qday／tg4 ＝ 計數 × 252 ／ eff，且＝舊值 × W／eff；A_* 不變；無 NaN')

def _qf(xs, N, lo=0): return metrics.quickfail_counts(xs, lo, N)                         # → (n, quick, pending)

def test_quickfail_last_bar_crossing_excluded():
    N = 100
    check(_qf([N - 1], N) == (0, 0, 1), '(a) 唯一穿越在最後一根：不計入分母（n=0、觀察中 1），不是 0% 成功')
    check(_qf([50, N - 1], N) == (1, 0, 1), '(a) 另有成熟穿越時：只有它計入（n=1），最後一根的穿越只算觀察中')
    check(_qf([N - 6], N) == (1, 0, 0) and _qf([N - 5], N) == (0, 0, 1), '成熟界線：t+5<=N-1（t=N-6 成熟、t=N-5 未成熟）')

def test_quickfail_mature_not_failed():
    N = 100
    check(_qf([N - 6], N) == (1, 0, 0), '(b) 後面有 5 根 K 棒且沒有再穿越：成熟、未快敗（n=1、quick=0）')
    check(_qf([40, 46], N) == (2, 0, 0) and _qf([40, 45], N) == (2, 1, 0), '快敗定義不變：下一次穿越相隔 <=5 才算（6 根不算、5 根算）')

def test_quickfail_immature_but_already_failed():
    N = 100
    check(_qf([N - 3, N - 2], N) == (1, 1, 1), '(c) 倒數第 3 根穿越、下一根又穿回：結果已知，算快敗（n=1、quick=1）；第二個穿越尚在觀察')
    check(_qf([N - 2, N - 1], N) == (1, 1, 1), '(c) 倒數第 2 根穿越、最後一根再穿回：計為快敗')
    check(_qf([10, 12], N, lo=11) == (1, 0, 0), '視窗起點 lo 之前的穿越不計')

def test_quickfail_end_to_end():
    for N_, last_cross in ((60, True), (60, False)):                          # 以真實計算流程驗證：最後一根才穿越 → quickfail 不把它當成功
        C = np.r_[np.full(N_ - 1, 110.), 90. if last_cross else 110.]; atr = np.ones(N_); ma = np.full(N_, 100.)
        xs = metrics.clear_crossings(C, ma, atr); assert xs == ([N_ - 1] if last_cross else [])
    check(True, 'clear_crossings 偵測最後一根穿越（供上面 (a) 的端到端對照）')

def test_no_nan_when_unevaluable():
    df = data.load(RAW / tickers(1)[0] / 'bars.csv').tail(60).reset_index(drop=True)    # period 110 > 60 棒：整段均線都是 NaN
    r = metrics.compute_metrics(df, (110,)).iloc[0]
    check(all(np.isfinite(r[f'{k}_{nm}']) and r[f'{k}_{nm}'] == 0 for k in ('tg4', 'qday') for nm, _ in YEARS), '完全不可評估（eff=0→夾成 1）：頻率為 0，不是 NaN／inf')

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f): print('#', n); f()
    print('PASS test_metrics_annualization：ALL PASS')
