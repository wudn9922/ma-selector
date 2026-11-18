# Past-only moving-average walk-forward research

This module evaluates the MA selector after freezing its choices at each training
cutoff. It creates each historical reference feature pool from that training
slice. It never reads today's `data/reference*.parquet` files.

Run an offline, bounded pilot from the frozen US archive:

```bash
python scripts/walk_forward_oos.py --source archive --tickers ADM,ADSK,AES \
  --asof 2026-09-29 --folds 3 --kinds SMA,EMA --include-v2 \
  --out experiments/walk_forward/pilot
```

The output directory must be empty. The runner accepts 2–30 unique symbols from
one market, 1–12 disjoint test folds, 21–252 test sessions per fold, training
history of 866–2520 sessions, cost multiplier 0–5 and adverse slippage 0–50 bps per
leg. It requires at least three eligible reference symbols by default (two is
available for deterministic tests). It emits source/fold coverage, past-only
reference snapshots, frozen selections, per-fold returns/drawdowns/turnover,
daily portfolio summaries, and the trade ledger as CSV; the Markdown report
records assumptions and limitations. No verification JSON or hashes are emitted.

The `walk-forward-oos-research` GitHub Actions workflow runs only by manual
dispatch. It fetches Yahoo history, compares SMA/EMA and optionally experimental
v2, uploads CSV/Markdown artifacts and writes a job summary. It has read-only
repository permissions and does not commit or publish anything. The workflow
has been created, not dispatched. A live Yahoo run is still required for a
larger US or Taiwan study; the frozen archive ends in September 2026.

`mark_to_market` and `legacy_exit` compare candidate-selection window accounting;
forward test capital always starts at the test boundary. Fixed MA20/40/60/100
baselines share the same folds and costs. Test folds start flat and liquidate at
their end. There is no publication hysteresis, financing/borrow model, historical
constituent roster, or delisted-symbol universe. A panel chosen today still has
selection and survivorship bias even with strictly past-only price calculations.

Execution sensitivity freezes the production SAR trade schedule. Current fills
reproduce `core.events` trade returns; optimistic uses fixed-band entries, while
conservative adds slippage and entry-bar opposite-band stop stress. The stressed
schedule does not regenerate reversals or retests. These scenarios are fill
stresses, not complete alternative state engines or guaranteed return bounds.
OHLC bars touching both bands and entry bars touching their opposite band are
counted. Complex long-only target/breakeven sequencing is outside this report.

Offline tests:

```bash
python -m unittest discover -s tests -p test_walk_forward_oos.py
```
