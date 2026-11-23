# Repository-wide agent rules

These rules apply to every directory in this repository. Read `README.md` before changing selector behavior: it records why each rule exists and how it was validated.

## Frozen production behavior

- **The production selector is frozen.** Rule B (5pp SAR finalists, highest unrounded structural score), the short-range `STRUCTURAL_RESCUE_10PT_10PP` thresholds (10.0 points / 10pp), `gap=15`, SMA as the default and the default weights change only when a task explicitly asks for it. New options go behind parameters whose defaults keep existing output byte-identical; the byte-identity tests (`tests/test_ma_kind.py`, `tests/test_backtest_entry_modes.py`, `tests/test_select_rescue.py`, ...) must keep passing unchanged.
- **Frozen evidence stays reproducible.** Never edit `regression/baselines/` (checked by `SHA256SUMS`) or the frozen records under `experiments/` (for example `experiments/holdout_v22/`). The legacy paths (`core.select.LEGACY`, `pct_mode='pooled'`, `smooth_mode='whole'`, `window_mode='legacy_exit'`) must keep reproducing them.
- **Reference distributions are generated.** `data/reference*.parquet` and `data/reference*.json` come from the `build-reference*` workflows. Do not regenerate or hand-edit them in a PR unless the task is about them.

## Downstream consumer: my-stock-screener

- `my-stock-screener`'s `ma-recommendations.yml` runs `scripts/build_recommendations.py`, and its Atlas chart reads the output (`atlas/src/report/maRecommendation.ts`).
- **Keep the recommendation JSON and `index.json` additive.** Never rename or remove a field or change its meaning; add fields only, and bump `VERSION` in `core/recommend.py` when you do.
- **Keep the CLI used by that workflow working:** `--tickers-file`, `--from-dir`, `--shard`, `--max-missing`, `--no-prune`, `--out`, `--workers`, `--limit`, `--min-success`.

## Tests and done

- `tests/test_*.py` are scripts: run them with `python tests/<file>.py`. `tests/test_window_accounting.py` is the exception: `python -m pytest -q tests/test_window_accounting.py`. Locally, run the tests related to the change.
- **A task is done only when every CI check on the PR's latest commit is green.** `.github/workflows/tests.yml` runs the whole suite on every PR. If a check fails, find the root cause and fix it before reporting the work as done; never report done while CI is still running or red. Never skip, disable or loosen a failing test.
- **Dependency versions must install everywhere they run.** The workflows use Python 3.11 and the web app runs on Streamlit Community Cloud. A constraint in `requirements.txt` or a workflow's `pip install` must be installable in all of them.
- The experiment and regression workflows have `contents: write` and commit reports back to `claude/**` branches. Do not add `pull_request` triggers to them; put PR checks in `tests.yml`, which is read-only.

## Before committing

- Run `git status` and make sure scripts or tests did not modify files under `data/`, `regression/` or `experiments/` unless the task is meant to change them. Revert such changes; never commit them.
- Never rewrite published history: no rebase, amend or force-push on a shared branch.
- PR description: short — what changed, why, how it was tested.
