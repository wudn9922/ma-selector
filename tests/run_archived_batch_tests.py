"""已封存批次（CURRENT_V22_FRESH_HOLDOUT_1、SAR confidence 診斷、STRUCTURAL_RESCUE_FRESH_VALIDATION_100）的測試。
這些測試會檢查「工作目錄的 production 檔案 ＝ 凍結時的 production」；加入 STRUCTURAL_RESCUE_10PT_10PP 後 core/select.py 依設計已不同，
所以在 HEAD 直接跑會失敗（預期行為）。本程式改在 git worktree（ARCHIVE_COMMIT＝加入 rescue 前最後一個 commit）裡跑原封不動的測試，
證明封存批次的證據仍然完整；同時確認 HEAD 的凍結檔案（freeze manifests、raw outputs、trigger summary、manual review）與 ARCHIVE_COMMIT 逐位元組相同。
用法：python tests/run_archived_batch_tests.py"""
import subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_COMMIT = '85b77549d2d785a649fb6f492a4a094b523595a6'
# 既有（與 rescue 無關）的已知失敗：開封前寫的檢查「repo 內沒有 raw outputs」，自 holdout 開封（bc3d73d）起本來就不成立。只容許這一條、且必須是唯一的 FAIL。
KNOWN_PREEXISTING = {'experiments/holdout_v22/test_run_holdout.py': 'FAIL 測試沒有在 repo 內留下任何 raw outputs 或 execution record'}
TESTS = ['experiments/holdout_v22/test_select_holdout.py', 'experiments/holdout_v22/test_run_holdout.py', 'experiments/sar_confidence/test_sar_confidence.py',
         'experiments/rescue_validation/test_freeze_rescue_validation.py', 'experiments/rescue_validation/test_run_validation.py']
FROZEN = ['experiments/holdout_v22/freeze_manifest.json', 'experiments/holdout_v22/freeze_manifest.md', 'experiments/holdout_v22/raw_outputs', 'experiments/holdout_v22/execution_record.json',
          'experiments/rescue_validation/freeze_manifest.json', 'experiments/rescue_validation/freeze_manifest.md', 'experiments/rescue_validation/raw_outputs', 'experiments/rescue_validation/execution_record.json',
          'experiments/rescue_validation/trigger_summary.json', 'experiments/rescue_validation/trigger_summary.md', 'experiments/rescue_validation/manual_review_results.json', 'experiments/rescue_validation/manual_review_results.md',
          'experiments/rescue_validation/review_bundle', 'regression/baselines', 'data/reference.parquet', 'core/events.py', 'core/score.py', 'core/metrics.py', 'core/universe.py']

def main():
    d = subprocess.run(['git', 'diff', '--name-only', ARCHIVE_COMMIT, '--'] + FROZEN, cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert not d, f'凍結檔案與 {ARCHIVE_COMMIT[:7]} 不同：{d}'; print(f'PASS 凍結檔案（{len(FROZEN)} 項）與 {ARCHIVE_COMMIT[:7]} 逐位元組相同')
    wt = Path(tempfile.mkdtemp(prefix='archived_')) / 'wt'; subprocess.run(['git', 'worktree', 'add', '--detach', str(wt), ARCHIVE_COMMIT], cwd=ROOT, check=True, capture_output=True)
    try:
        bad = []
        for t in TESTS:
            r = subprocess.run([sys.executable, t], cwd=wt, capture_output=True, text=True)
            fails = [l for l in r.stdout.splitlines() if l.startswith('FAIL ')]
            known = r.returncode != 0 and t in KNOWN_PREEXISTING and fails == [KNOWN_PREEXISTING[t]] and fails[0] == r.stdout.strip().splitlines()[-1]   # 唯一的 FAIL，且是最後一個檢查
            print(('PASS ' if r.returncode == 0 else 'PASS（只有既有已知失敗：' + KNOWN_PREEXISTING[t][5:] + '）' if known else 'FAIL ') + f'{t}（在 {ARCHIVE_COMMIT[:7]} worktree）')
            if r.returncode and not known: bad.append(t); print(r.stdout[-1500:], r.stderr[-1500:])
        assert not bad, bad; print('ALL PASS')
    finally: subprocess.run(['git', 'worktree', 'remove', '--force', str(wt)], cwd=ROOT, capture_output=True)

if __name__ == '__main__': main()
