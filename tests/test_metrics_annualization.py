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
        pd.testing.assert_frame_equal(metrics.compute_metrics(df), orig.compute_metrics(df), check_exact=True)
    check(True, f'完整歷史 {len(ts)} 檔：compute_metrics 與 {BASE_COMMIT[:7]} 的版本逐位元組相同（assert_frame_equal check_exact）')

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
                assert new.loc[p, f'quickfail_{nm}'] == old.loc[p, f'quickfail_{nm}']          # 比率不受影響
            ev = [c for c in new.columns if c.startswith('A_')]
            pd.testing.assert_frame_equal(new.loc[[p], ev], old.loc[[p], ev], check_exact=True)  # 事件成功率不變
        assert not new.filter(regex='^(tg4|qday)_').isna().any().any()
        check(True, f'{tk}（最後 450 棒；period 20／60／110；1y／2y／3y）：qday／tg4 ＝ 計數 × 252 ／ eff，且＝舊值 × W／eff；quickfail 與 A_* 不變；無 NaN')

def test_no_nan_when_unevaluable():
    df = data.load(RAW / tickers(1)[0] / 'bars.csv').tail(60).reset_index(drop=True)    # period 110 > 60 棒：整段均線都是 NaN
    r = metrics.compute_metrics(df, (110,)).iloc[0]
    check(all(np.isfinite(r[f'{k}_{nm}']) and r[f'{k}_{nm}'] == 0 for k in ('tg4', 'qday') for nm, _ in YEARS), '完全不可評估（eff=0→夾成 1）：頻率為 0，不是 NaN／inf')

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f): print('#', n); f()
    print('PASS test_metrics_annualization：ALL PASS')
