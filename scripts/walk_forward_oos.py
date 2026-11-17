"""Manual, bounded research run; no production files or remote state are changed."""
import argparse
from dataclasses import asdict
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import data
from experiments.walk_forward.engine import Config, run, summaries


def csv_choices(value):
    return tuple(v.strip() for v in value.split(',') if v.strip())


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', choices=('archive', 'yahoo'), default='archive')
    p.add_argument('--data-dir', type=Path, default=ROOT / 'experiments/rescue_validation/raw_outputs')
    p.add_argument('--tickers', default='ADM,ADSK,AES')
    p.add_argument('--asof', default='2026-09-29')
    p.add_argument('--range', choices=('5y', '10y'), default='10y', dest='yahoo_range')
    p.add_argument('--train-bars', type=int, default=1008)
    p.add_argument('--test-bars', type=int, default=63)
    p.add_argument('--folds', type=int, default=4)
    p.add_argument('--kinds', type=csv_choices, default=('SMA',))
    p.add_argument('--window-modes', type=csv_choices, default=('mark_to_market', 'legacy_exit'))
    p.add_argument('--include-v2', action='store_true')
    p.add_argument('--fixed-periods', type=lambda x: tuple(int(v) for v in csv_choices(x)), default=(20, 40, 60, 100))
    p.add_argument('--cost-multiplier', type=float, default=1.)
    p.add_argument('--slippage-bps', type=float, default=5.)
    p.add_argument('--min-reference', type=int, default=3)
    p.add_argument('--out', type=Path, default=ROOT / 'experiments/walk_forward/output')
    return p


def load_panel(args):
    tickers = csv_choices(args.tickers.upper())
    if not 2 <= len(tickers) <= 30 or len(set(tickers)) != len(tickers) or any(not re.fullmatch(r'[A-Z0-9][A-Z0-9.^-]{0,15}', t) for t in tickers):
        raise ValueError('provide 2..30 unique ticker symbols')
    asof = pd.Timestamp(args.asof)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.asof) or pd.isna(asof) or asof.tzinfo is not None:
        raise ValueError('asof must be an unzoned YYYY-MM-DD date')
    panel, coverage = {}, []
    for ticker in tickers:
        try:
            if args.source == 'archive':
                path = args.data_dir / ticker / 'bars.csv'
                if not path.exists():
                    path = args.data_dir / f'{ticker}.csv'
                frame = data.load(path, asof)
                adjusted = 'unknown (frozen CSV has no adjustment metadata)'
                source = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
            else:
                frame = data.normalize(data.fetch_yahoo(ticker, rng=args.yahoo_range, adjust=True), asof)
                adjusted = str(bool(frame.attrs.get('adjusted')))
                source = f'Yahoo daily {args.yahoo_range}; downloaded at run time'
            if frame.empty:
                raise ValueError('no rows through requested asof')
            panel[ticker] = frame
            coverage.append(dict(ticker=ticker, loaded=True, source=source, adjusted=adjusted, bars=len(frame),
                                 first_date=frame.date.iloc[0], last_date=frame.date.iloc[-1], error=''))
            print(f'{ticker}: {len(frame)} bars through {frame.date.iloc[-1].date()}', flush=True)
        except Exception as exc:
            coverage.append(dict(ticker=ticker, loaded=False, source=args.source, error=str(exc)))
            print(f'{ticker}: unavailable ({exc})', flush=True)
    return panel, pd.DataFrame(coverage)


def markdown_table(frame, cols, limit=48):
    if frame.empty:
        return 'No eligible observations.'
    sub = frame[cols].head(limit).copy()
    for col in sub:
        if col.endswith('return') or col.endswith('drawdown'):
            sub[col] = sub[col].map(lambda x: f'{x:.2%}')
        elif pd.api.types.is_float_dtype(sub[col]):
            sub[col] = sub[col].map(lambda x: f'{x:.2f}')
    lines = ['| ' + ' | '.join(sub.columns) + ' |', '| ' + ' | '.join('---' for _ in sub.columns) + ' |']
    lines += ['| ' + ' | '.join(str(v) for v in row) + ' |' for row in sub.itertuples(index=False, name=None)]
    if len(frame) > limit:
        lines.append(f'\nFirst {limit}/{len(frame)} rows; complete table is in CSV.')
    return '\n'.join(lines)


def write_report(out, args, config, tables, sources, summary, turnover):
    fold_text = markdown_table(tables['folds'], ['fold', 'train_start', 'train_end', 'test_start', 'test_end'])
    primary = summary[(summary.report_period == 'all') & (summary.scenario == 'current')]
    cols = ['kind', 'window_mode', 'strategy', 'range', 'net_return', 'max_drawdown', 'sessions', 'min_tickers']
    sensitivity = summary[summary.report_period == 'all']
    text = f'''# Moving-average walk-forward research

Status: research framework and bounded {'archived-data pilot' if args.source == 'archive' else 'Yahoo-data run'}, not a prospective validation or a production adoption decision.

## Boundaries and fixed parameters

Requested as-of: {args.asof}. Source: {args.source}. Loaded {int(sources.loaded.sum())}/{len(sources)} requested symbols. Actual source coverage and failures: `source_coverage.csv`.

{fold_text}

Configuration fixed before this run: `{asdict(config)}`.

For each fold and MA kind, indicators and event outcomes are computed on the train slice only. Percentile reference pools are rebuilt from that same past-only panel, independently for SMA, EMA, and v2. The repository's current `data/reference*.parquet` files are never read. `reference_features.csv` records the actual feature/reference snapshot and as-of; `selections.csv` records the selected period, training candidate return, reference membership, and bounds. The target symbol is included in this cross-sectional reference pool. Minimum history 866 bars permits 756 observed sessions plus the longest MA warmup. Full training histories shorter than the configured maximum are allowed and disclosed in `coverage.csv`.

Each test fold starts flat, warms MA/ATR on training history, freezes its chosen period, and liquidates at its last close. Costs are each market's fixed round-trip cost × cost multiplier, charged half on entry and half on exit. Boundary liquidation/re-entry costs are included, even when adjacent folds choose the same MA. Full-notional SAR supports shorts; borrow fees, financing, margin, liquidity, bid/ask variation, and taxes beyond the configured flat cost are absent. This is not the production app's long-only complex strategy.

`window_mode` changes the historical candidate selection return accounting (legacy exit-attributed versus interval mark-to-market); honest forward test returns always use new capital at the test start. Thus the comparison measures the downstream selection effect of the window fix. Batch publication hysteresis is absent. v2, when requested, evaluates short1 and available short2 as separate signals and medium independently; it does not imply a combined two-line portfolio. Missing short2 observations have their own coverage and cannot be compared as a matched full cohort.

## Current execution: selected and fixed MA baselines

Daily returns are averaged equally across the eligible symbols for each strategy, then compounded across disjoint test blocks. This is a daily rebalanced research portfolio; portfolio rebalancing costs are not modeled. Fixed MA20/40/60/100 (or the explicitly supplied alternatives) use the same warmup, test blocks, costs and SAR execution. `summary.csv` includes full-period and calendar-year return/drawdown; `fold_results.csv` preserves the period-by-period results. Portfolio rows disclose minimum symbol count. Full-notional turnover is the number of entry/exit legs (2 per completed trade), annualized by actual test sessions; `turnover.csv` includes mean per-symbol/fold turnover and counts, not dollar-volume capacity.

{markdown_table(primary, cols)}

## Execution sensitivity

These are **fixed production-schedule fill stresses, not alternative signal-state backtests or guaranteed performance bounds**. `current` reproduces production `core.events.events` schedule and net trade returns with gap-open fills. Its intraday stop rule ignores the entry bar. `optimistic` uses the fixed MA boundary entry even if a gap makes that price unattainable; exit schedule/prices are retained. `conservative` applies {config.slippage_bps:g} bps adverse slippage to both legs and immediately exits an entry bar touching the opposite MA band, at that boundary or a worse open. It then stays flat until the next originally scheduled entry. Reversals/retests are not regenerated after a stressed exit. The labels express assumptions and need not produce an ordered return ranking.

Ambiguity counts: `both_band_bars` = test OHLC touches both MA bands, regardless of position; `ambiguous_entry_bars` = scheduled entry bar also touches its opposite band. Counts are per strategy/symbol/fold, so sums across different strategies duplicate market bars. They expose uncertainty in daily OHLC ordering; neither count proves an actual intraday stop. Target/stop races affect the selector's historical event features but SAR execution has no profit target; this report does not claim sensitivity coverage for the long-only complex strategy's target/breakeven sequencing.

{markdown_table(sensitivity, ['kind', 'window_mode', 'strategy', 'range', 'scenario', 'net_return', 'max_drawdown'], 96)}

{markdown_table(turnover, ['kind', 'window_mode', 'strategy', 'range', 'scenario', 'mean_turnover_annualized', 'both_band_bars', 'ambiguous_entry_bars'], 96)}

## Limits and interpretation

The archived US pilot ends in September 2026; it contains no November or Taiwan evidence. Frozen CSV adjustment metadata is unknown. A live Yahoo run may contain adjusted OHLC, with status recorded per symbol, but Yahoo history can be revised and is not a point-in-time archive. Symbols and selector rules were chosen using present knowledge: survivorship, historical-universe selection and prior development overlap remain. No historical constituent roster or delisted-symbol return coverage is claimed. A past-only rolling calculation prevents mechanical future-price/reference leakage but does not remove those study-design biases. A small pilot cannot establish superiority, and no test results are used to tune parameters automatically. Selection/missing-data counts and CSV results should be reviewed before any adoption claim. A frozen universe and prospective follow-up would be needed for a stronger conclusion.

Manual GitHub Actions can fetch a larger Yahoo panel and upload these CSV/Markdown artifacts. The workflow has no schedule, push trigger, commits, publishing, or automatic dispatch. The runner writes no verification JSON or hash-based evidence.
'''
    (out / 'report.md').write_text(text, encoding='utf-8')
    stress = summary[(summary.report_period == 'all') & (summary.window_mode == 'mark_to_market')
                     & summary.strategy.isin(['selector', 'v2'])]
    wide = stress.pivot(index=['kind', 'strategy', 'range'], columns='scenario', values='net_return').reset_index()
    counts = turnover[(turnover.window_mode == 'mark_to_market') & (turnover.scenario == 'current')]
    wide = wide.merge(counts[['kind', 'strategy', 'range', 'both_band_bars', 'ambiguous_entry_bars', 'mean_turnover_annualized']],
                      on=['kind', 'strategy', 'range'], how='left')
    for col in config.scenarios:
        if col in wide:
            wide[col] = wide[col].map(lambda v: f'{v:.2%}')
    sensitivity_text = f'''# SAR execution sensitivity — fixed schedule

Source: {args.source}; requested as-of {args.asof}; {int(sources.loaded.sum())} loaded symbols; {len(tables['folds'])} disjoint folds. These results do not change the production execution default.

The table uses the new interval accounting to choose each fold's MA, then freezes the production SAR event schedule. Returns are equal-weight daily portfolio returns after the configured market costs; drawdowns and fixed baselines are in `summary.csv`. Full-notional annual turnover counts entry/exit legs.

{markdown_table(wide, list(wide.columns), 48)}

`current` matches the production event schedule and each net trade return exactly, with gap-open entries. `optimistic` replaces entry fills with fixed band prices; these can be unattainable after a gap. `conservative` adds {config.slippage_bps:g} bps adverse slippage on each leg and stops an entry bar at its opposite band (or worse open) when both are touched. It waits flat for the next originally scheduled entry. This stress does not recompute endogenous reversals or retests and is not a complete alternate execution engine or a guaranteed bound. Daily OHLC does not establish intraday ordering.

`both_band_bars` counts test bars touching both MA bands, irrespective of position. `ambiguous_entry_bars` counts scheduled entry bars also touching their opposite band. Different strategies may count the same market bar. No target-stop ordering claim is made for the app's complex long-only strategy: SAR has no target exit. Small reference pools, present-day symbol selection, historical-universe/survivorship bias, absent borrow/financing, and archived adjustment uncertainty limit interpretation. See `report.md` for train/test boundaries, source coverage, portfolio assumptions and limitations.
'''
    (out / 'execution_sensitivity.md').write_text(sensitivity_text, encoding='utf-8')


def main(argv=None):
    args = parser().parse_args(argv)
    config = Config(train_bars=args.train_bars, test_bars=args.test_bars, folds=args.folds,
                    kinds=args.kinds, window_modes=args.window_modes, include_v2=args.include_v2,
                    fixed_periods=args.fixed_periods, slippage_bps=args.slippage_bps,
                    cost_multiplier=args.cost_multiplier, min_reference=args.min_reference)
    config.validate()
    if args.out.exists() and any(args.out.iterdir()):
        raise ValueError('output directory must be empty; use a new directory to avoid mixing research runs')
    args.out.mkdir(parents=True, exist_ok=True)
    panel, sources = load_panel(args)
    sources.to_csv(args.out / 'source_coverage.csv', index=False)
    if len(panel) < config.min_reference:
        raise ValueError('not enough loaded symbols for the explicit minimum reference pool')
    tables = run(panel, config)
    names = dict(results='fold_results', selections='selections', coverage='coverage', folds='folds',
                 daily='daily_returns', trades='trade_ledger', reference_features='reference_features')
    for key, table in tables.items():
        table.to_csv(args.out / f'{names[key]}.csv', index=False)
    if tables['results'].empty:
        raise ValueError('no eligible complete test folds; inspect source_coverage.csv and coverage.csv')
    summary, turnover = summaries(tables)
    summary.to_csv(args.out / 'summary.csv', index=False)
    turnover.to_csv(args.out / 'turnover.csv', index=False)
    write_report(args.out, args, config, tables, sources, summary, turnover)
    print(f'Wrote {len(tables["results"])} symbol/fold/scenario rows to {args.out}', flush=True)


if __name__ == '__main__':
    main()
