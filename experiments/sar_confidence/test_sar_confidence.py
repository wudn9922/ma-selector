"""sar_confidence_experiment 的測試（純合成資料；不連網）。用法：python experiments/sar_confidence/test_sar_confidence.py"""
import hashlib, json, subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'experiments' / 'sar_confidence'), str(ROOT / 'research'), str(ROOT / 'scripts')]
import sar_confidence_experiment as X
from core import select as sel

def walk(seed, N=900, vol=.02):
    rng = np.random.default_rng(seed); C = 100 * np.exp(np.cumsum(rng.normal(.0003, vol, N))); O = np.r_[C[0], C[:-1]] * (1 + rng.normal(0, .004, N))
    H = np.maximum(O, C) * (1 + np.abs(rng.normal(0, .008, N))); L = np.minimum(O, C) * (1 - np.abs(rng.normal(0, .008, N)))
    import pandas as pd
    df = pd.DataFrame(dict(open=O, high=H, low=L, close=C)); pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return O, H, L, C, tr.ewm(alpha=1 / 14, adjust=False).mean().to_numpy(), df.close

def test_reconstruction():
    """逐日重建的複利報酬 = production sar_stats()['報酬']（≤1e-12）；含視窗起點落在持倉中間、多種 MA、多種 seed／波動"""
    worst = 0.
    for seed in range(6):
        O, H, L, C, atr, close = walk(seed, vol=.012 + .006 * seed)
        for p in (15, 19, 24, 27, 33):
            ma = close.rolling(p).mean().to_numpy()
            for lo in (len(C) - 252, len(C) - 100, 300):
                rets, eq, tot = X.sar_daily_returns(O, H, L, C, atr, ma, lo); prod = sel.sar_stats(O, H, L, C, atr, ma, lo)
                assert len(rets) == len(C) - lo
                worst = max(worst, abs(X.compound(rets) - prod['報酬']), abs(tot - prod['報酬']))
                seg = np.r_[1., eq]; assert abs(float((seg / np.maximum.accumulate(seg) - 1).min()) - prod['回撤']) <= 1e-12
    assert worst <= 1e-12, worst; print(f'  重建最大誤差 {worst:.2e}')

def test_circular_blocks():
    for L in (5, 10, 20):
        for n in (252, 37):
            rng = np.random.default_rng(1); idx = X.block_indices(n, L, 50, rng); assert idx.shape == (50, n) and idx.min() >= 0 and idx.max() < n
            for row in idx:
                for a in range(0, n - 1):
                    if (a + 1) % L != 0: assert row[a + 1] == (row[a] + 1) % n          # 區塊內連續（循環）
    idx = X.indices_from_starts(np.array([[8, 3]]), 10, 4); assert idx.tolist() == [[8, 9, 0, 1, 3, 4, 5, 6]], idx.tolist()          # n 大於區塊總長時不補（僅測 wrap）
    idx = X.indices_from_starts(np.array([[8, 3, 0]]), 10, 4); assert idx.tolist() == [[8, 9, 0, 1, 3, 4, 5, 6, 0, 1]], idx.tolist()   # 循環環繞＋截斷成 n
    print('  circular blocks OK')

def test_seed_deterministic():
    rets = np.random.default_rng(0).normal(0, .01, (3, 252))
    r1 = X.gap_stats(rets, 10, 2000, np.random.default_rng(X.SEED)); r2 = X.gap_stats(rets, 10, 2000, np.random.default_rng(X.SEED)); r3 = X.gap_stats(rets, 10, 2000, np.random.default_rng(X.SEED + 1))
    assert (r1['count_gap'] == r2['count_gap']).all() and (r1['count_best'] == r2['count_best']).all() and not (r1['count_gap'] == r3['count_gap']).all()
    a = X.gap_stats(rets, 10, 2000, np.random.default_rng(X.SEED), chunk=2000); b = X.gap_stats(rets, 10, 2000, np.random.default_rng(X.SEED), chunk=300)
    assert (a['count_gap'] == b['count_gap']).all()                                        # 結果不受 chunk 大小影響
    for L in (5, 10, 20): X.gap_stats(rets, L, 500, np.random.default_rng(X.SEED))
    print('  deterministic seed OK; L=5/10/20 OK')

def test_paired_indices(monkeypatch=None):
    """所有候選共用同一批 idx：兩個候選日報酬完全相同 → 每次重抽 GAP 皆為 0（若各自重抽就不會）；bootstrap_R 對所有候選只收到一份 idx"""
    r = np.random.default_rng(3).normal(0, .01, 252); g = X.gap_stats(np.vstack([r, r]), 10, 3000, np.random.default_rng(1))
    assert (g['count_gap'] == 0).all() and (g['count_best'] == 3000).all()
    seen = []; orig = X.bootstrap_R
    def spy(m, idx): seen.append(idx.copy()); return orig(m, idx)
    X.bootstrap_R = spy
    try: X.gap_stats(np.random.default_rng(4).normal(0, .01, (4, 252)), 10, 1000, np.random.default_rng(5), chunk=1000)
    finally: X.bootstrap_R = orig
    assert len(seen) == 1                                                                   # 4 個候選、1 次呼叫、1 份 idx
    m = np.random.default_rng(6).normal(0, .01, (3, 252)); idx = X.block_indices(252, 10, 20, np.random.default_rng(7)); R = X.bootstrap_R(m, idx)
    for j in range(3):
        for b in range(20): assert abs(R[j, b] - (np.prod(1 + m[j][idx[b]]) - 1)) < 1e-12   # 同一 idx[b] 套到每個候選
    print('  paired indices OK')

def test_best_recomputed_each_replicate():
    """BEST[b] 每次重抽重算：對照純 Python 迴圈；且觀察到的冠軍在某些重抽中 GAP>0"""
    rng0 = np.random.default_rng(11); m = rng0.normal(0, .012, (4, 120)); m[0] += .0009
    reps, L = 1500, 10; g = X.gap_stats(m, L, reps, np.random.default_rng(9), chunk=400)
    rng = np.random.default_rng(9); starts = rng.integers(0, 120, size=(reps, 12)); cg = np.zeros(4, int); cb = np.zeros(4, int)
    for b in range(reps):
        idx = np.concatenate([(s + np.arange(L)) % 120 for s in starts[b]])[:120]; Rb = np.array([np.prod(1 + m[j][idx]) - 1 for j in range(4)]); BEST = Rb.max()
        cg += (BEST - Rb > X.PP); cb += (Rb >= BEST)
    assert (g['count_gap'] == cg).all() and (g['count_best'] == cb).all()
    obs = int(np.argmax([np.prod(1 + m[j]) - 1 for j in range(4)])); assert g['count_best'][obs] < reps and g['count_gap'][obs] > 0     # 觀察冠軍並非每次都是 BEST
    print('  BEST recomputed per replicate OK')

def test_finalist_boundary():
    C = [dict(period=20, s=50., r=.50, n=10), dict(period=25, s=60., r=.40, n=10), dict(period=30, s=55., r=.30, n=10)]
    reps = 20000
    assert X.survives(18999, reps, 95) and not X.survives(19000, reps, 95) and not X.survives(19001, reps, 95)      # ≥95% 剔除（含等號）
    assert X.survives(17999, reps, 90) and not X.survives(18000, reps, 90)
    assert X.finalists_ca(C, [0, 18999, 19000], reps, 95) == [20, 25]
    assert X.finalists_ca(C, [0, 18000, 19000], reps, 90) == [20]
    assert X.finalists_ca(C, [19999, 0, 0], reps, 95) == [20, 25, 30]                      # 觀察 SAR 最高者一律保留（即使機率≥95%）
    assert X.finalists_rule_b(C) == [20] and X.pick_ca(C, [0, 0, 0], reps, 95) == 25       # 沒有候選被剔除 → 取結構分最高
    # 5pp cliff：4.99pp 存活、5.01pp 被剔除（規則 B）
    D = [dict(period=20, s=40., r=.500, n=1), dict(period=25, s=60., r=.4501, n=1)]; assert X.pick_rule_b(D) == 25
    D[1]['r'] = .4499; assert X.pick_rule_b(D) == 20
    print('  finalist probability boundary OK')

def test_structural_tie_shorter():
    C = [dict(period=30, s=55.5, r=.3, n=1), dict(period=22, s=55.5, r=.3, n=1), dict(period=26, s=55.5, r=.3, n=1)]
    assert X.pick_rule_b(C) == 22 and X.pick_ca(C, [0, 0, 0], 20000, 95) == 22 and X.struct_best(C) == 22
    C2 = [dict(period=30, s=55.5000001, r=.3, n=1), dict(period=22, s=55.5, r=.3, n=1)]; assert X.pick_rule_b(C2) == 30     # 未四捨五入：微小差異也算
    print('  exact structural tie -> shorter MA OK')

def test_posthoc_and_external():
    ex = [dict(period=p, s=v[0], r=v[1], n=v[2]) for p, v in X.EXTERNAL.items()]
    assert X.pick_rule_b(ex) == 19 and X.pick_posthoc(ex) == 29
    weak = [dict(ex[0], s=55.0)] + ex[1:]; assert X.pick_posthoc(weak) == 19                # 結構分只高 8.5 → 不救
    far = [dict(ex[0], r=.70)] + ex[1:]; assert X.pick_posthoc(far) == 19                   # SAR 差距 11.5pp → 不救
    two = [dict(period=20, s=50., r=.5, n=1), dict(period=25, s=70., r=.44, n=1)]; assert X.pick_rule_b(two) == 20 and X.pick_posthoc(two) == 25   # 6pp 差距被 5pp 門檻剔除，但結構分高 20、SAR 差 ≤10pp → 救回
    print('  posthoc control OK')

def test_stats():
    assert X.mcnemar_exact(0, 0) == 1.0 and abs(X.mcnemar_exact(5, 0) - 0.0625) < 1e-12 and abs(X.mcnemar_exact(3, 3) - 1.0) < 1e-12
    m, lo, hi = X.paired_boot_mean_diff(np.zeros(20), 500); assert (m, lo, hi) == (0., 0., 0.)
    m2 = X.paired_boot_mean_diff(np.r_[-np.ones(10), np.zeros(10)], 2000); assert m2[0] == -.5 and m2[1] < m2[0] < m2[2]
    assert X.paired_boot_mean_diff(np.arange(10), 300) == X.paired_boot_mean_diff(np.arange(10), 300)
    print('  stats OK')

def test_no_production_changes():
    man = json.loads((ROOT / 'experiments/holdout_v22/freeze_manifest.json').read_text())['production']['file_sha256_at_production_commit']
    for k, h in man.items(): assert hashlib.sha256((ROOT / k).read_bytes()).hexdigest() == h, f'{k} 與 production commit 不同'
    forbidden = ('core/', 'app.py', 'data/reference', 'README.md', 'experiments/holdout_v22/', 'experiments/final_rules/', 'regression/', 'research/', 'requirements.txt', 'packages.txt')
    base = '1359ea2'
    if subprocess.run(['git', 'cat-file', '-e', base], cwd=ROOT, capture_output=True).returncode == 0:
        ch = subprocess.run(['git', 'diff', '--name-only', base], cwd=ROOT, capture_output=True, text=True).stdout.split()
        ch += subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, capture_output=True, text=True).stdout.split()
        bad = [f for f in ch if f.startswith(forbidden)]; assert not bad, f'不得修改：{bad}'
    print('  no production file changes OK')

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f): print(n); f()
    print('PASS: all sar_confidence tests')
