"""Causal research harness. Never loads the repository's current reference files.

Selection is frozen before each disjoint test block. Execution scenarios replay
the same production SAR trade schedule; stressed fills do not re-run signal state.
"""
from dataclasses import dataclass
from pathlib import Path
import inspect

import numpy as np
import pandas as pd

from core import data, events, metrics, score, score_v2, select, select_v2
from core.ma import moving_average
from core.market import cost_of, market_of

WINDOW_MODES = ('mark_to_market', 'legacy_exit')
SCENARIOS = ('current', 'optimistic', 'conservative')
RANGE_KEYS = {'短期': 'short', '中期': 'medium', '長期': 'long'}


@dataclass(frozen=True)
class Config:
    train_bars: int = 1008
    min_train_bars: int = 866
    test_bars: int = 63
    folds: int = 4
    kinds: tuple = ('SMA',)
    window_modes: tuple = WINDOW_MODES
    include_v2: bool = False
    fixed_periods: tuple = (20, 40, 60, 100)
    scenarios: tuple = SCENARIOS
    slippage_bps: float = 5.0
    cost_multiplier: float = 1.0
    min_reference: int = 3

    def validate(self):
        if not 866 <= self.min_train_bars <= self.train_bars <= 2520:
            raise ValueError('training history must satisfy 866 <= minimum <= train <= 2520')
        if not 21 <= self.test_bars <= 252 or not 1 <= self.folds <= 12:
            raise ValueError('test bars must be 21..252; folds must be 1..12')
        for values, allowed in ((self.kinds, ('SMA', 'EMA')), (self.window_modes, WINDOW_MODES), (self.scenarios, SCENARIOS)):
            if not values or len(set(values)) != len(values) or any(x not in allowed for x in values):
                raise ValueError(f'invalid or duplicate choices: {values}')
        if not self.fixed_periods or len(set(self.fixed_periods)) != len(self.fixed_periods) or any(not 15 <= x <= 110 for x in self.fixed_periods):
            raise ValueError('fixed MA periods must be unique and in 15..110')
        if not 0 <= self.slippage_bps <= 50 or not 0 <= self.cost_multiplier <= 5 or not 2 <= self.min_reference <= 100:
            raise ValueError('slippage 0..50bps; cost multiplier 0..5; minimum reference 2..100')


def clean_frame(frame):
    frame = data.normalize(frame)
    a = frame[['open', 'high', 'low', 'close']].to_numpy(float)
    if not np.isfinite(a).all() or (a <= 0).any():
        raise ValueError('OHLC must be finite positive values')
    if ((frame.low > frame[['open', 'close']].min(axis=1)) | (frame.high < frame[['open', 'close']].max(axis=1))).any():
        raise ValueError('OHLC outside high/low envelope')
    return frame


def make_folds(panel, config):
    """Use a common market-session calendar; test blocks never overlap."""
    config.validate()
    if len({market_of(t) for t in panel}) != 1:
        raise ValueError('one market per run; do not mix US and TW sessions/reference pools')
    calendar = pd.DatetimeIndex(sorted(set().union(*(set(d.date) for d in panel.values()))))
    n = len(calendar)
    available = min(config.folds, max(0, (n - config.min_train_bars) // config.test_bars))
    if not available:
        raise ValueError('no full test fold after minimum training history')
    folds = []
    for i in range(available):
        stop = n - (available - 1 - i) * config.test_bars
        start = stop - config.test_bars
        folds.append(dict(fold=i + 1, train_start=calendar[max(0, start - config.train_bars)],
                          train_end=calendar[start - 1], test_start=calendar[start], test_end=calendar[stop - 1]))
    return folds


def training_snapshot(panel, fold, kind, config):
    """Feature and reference snapshots contain only rows inside the train bounds."""
    frames, tables, audit = {}, {}, []
    for ticker, full in sorted(panel.items()):
        train = full[(full.date >= fold['train_start']) & (full.date <= fold['train_end'])].reset_index(drop=True)
        good = len(train) >= config.min_train_bars and len(train) and train.date.iloc[-1] == fold['train_end']
        audit.append(dict(fold=fold['fold'], kind=kind, ticker=ticker, stage='training', train_start=fold['train_start'],
                          train_end=fold['train_end'], last_observed=train.date.iloc[-1] if len(train) else None,
                          train_bars=len(train), included=bool(good), reason='' if good else 'short history or stale at training end'))
        if good:
            frames[ticker] = train
            tables[ticker] = metrics.compute_metrics(train, kind=kind)
    if len(tables) < config.min_reference:
        return frames, tables, None, None, audit
    reference = pd.concat([score.make_features(m).assign(ticker=t) for t, m in tables.items()], ignore_index=True)
    reference_v2 = pd.concat([score_v2.make_features_v2(m).assign(ticker=t) for t, m in tables.items()], ignore_index=True) if config.include_v2 else None
    return frames, tables, reference, reference_v2, audit


def _window_kwargs(fn, mode):
    if 'window_mode' not in inspect.signature(fn).parameters:
        raise RuntimeError('walk-forward requires the explicit core window_mode API')
    return {'window_mode': mode}


def choose(train, table, reference, reference_v2, ticker, kind, mode, config):
    """Production selection without batch hysteresis; all arguments are train-only."""
    cost = cost_of(ticker) * config.cost_multiplier
    selected = select.select(train, score.score_table(table, reference), kind=kind, cost=cost, **_window_kwargs(select.select, mode))
    rows = []
    for name, group in selected.items():
        candidate = next(c for c in group['cands'] if c['均線'] == group['final'])
        rows.append(dict(strategy='selector', range=RANGE_KEYS[name], period=int(group['final']),
                         train_sar_return=candidate['反手報酬'], candidate_periods=' '.join(str(c['均線']) for c in group['cands'])))
    if config.include_v2:
        v2 = select_v2.select_v2(train, table, reference_v2, kind=kind, cost=cost, **_window_kwargs(select_v2.select_v2, mode))
        for name, period in (('short1', v2['短期']['final1']), ('short2', v2['短期']['final2']), ('medium', v2['中期']['final'])):
            if period is not None:
                rows.append(dict(strategy='v2', range=name, period=int(period), train_sar_return=np.nan, candidate_periods=''))
    return rows


def production_schedule(frame, period, kind, test_start, cost):
    """Start flat at test_start with indicators warmed on past data.

    ATR masking suppresses pre-test trades and retest state. Production event
    results include forward event labels, but only its causal trade ledger is
    consumed here. The schedule/fills exactly match events() on these inputs.
    """
    lo = int(frame.date.searchsorted(pd.Timestamp(test_start)))
    if lo < 1 or lo >= len(frame):
        raise ValueError('test requires at least one preceding indicator bar and one test bar')
    O, H, L, C = (frame[c].to_numpy(float) for c in ('open', 'high', 'low', 'close'))
    ma = moving_average(frame.close, period, kind)
    atr = data.wilder_atr(frame).copy()
    atr[:lo] = np.nan
    _, _, _, positions, trades = events.events(O, H, L, C, ma, atr, cost=cost)
    entries = {(a, b, side, k): (e, x) for a, b, side, e, x, k in positions}
    prior = np.r_[np.nan, ma[:-1]]
    upper, lower = prior * 1.01, prior * .985
    ledger = []
    for tin, tout, side, ret, tag in trades:
        entry, exit_ = entries.get((tin, tout, side, tag),
                                  (max(O[tin], upper[tin]) if side == 1 else min(O[tin], lower[tin]), C[tout]))
        ledger.append(dict(tin=tin, tout=tout, side=side, entry=entry, exit=exit_, production_return=ret, tag=tag))
    both = (H[lo:] >= upper[lo:]) & (L[lo:] <= lower[lo:])
    return ledger, lo, upper, lower, int(both.sum())


def replay(frame, period, kind, test_start, scenario='current', cost=.001, slippage_bps=5):
    """Reprice a frozen production schedule, and count unresolved intrabar bars.

    Optimistic = no adverse slippage, entry at fixed band (including gaps).
    Conservative = current gap fills plus adverse slippage on both legs; an
    entry bar touching the opposite band exits at that band (or worse open).
    Later scheduled entries remain fixed. These are stresses, not bounds.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f'invalid scenario: {scenario}')
    ledger, lo, upper, lower, both_count = production_schedule(frame, period, kind, test_start, cost)
    n = len(frame)
    eq = np.ones(n - lo)
    capital, ambiguous, entry_gap_count = 1., 0, 0
    rows = []
    for tr in ledger:
        tin, tout, side = tr['tin'], tr['tout'], tr['side']
        entry, exit_ = tr['entry'], tr['exit']
        band = upper[tin] if side == 1 else lower[tin]
        opposite = lower[tin] if side == 1 else upper[tin]
        touched = frame.low.iloc[tin] <= opposite if side == 1 else frame.high.iloc[tin] >= opposite
        ambiguous += bool(touched)
        entry_gap_count += abs(entry - band) > 1e-10
        if scenario == 'optimistic':
            entry = band
        elif scenario == 'conservative':
            if touched:
                tout = tin
                exit_ = min(frame.open.iloc[tin], opposite) if side == 1 else max(frame.open.iloc[tin], opposite)
            slip = slippage_bps / 10000
            entry *= 1 + side * slip
            exit_ *= 1 - side * slip
        gross = side * (exit_ / entry - 1)
        ret = gross - cost
        if ret <= -1:
            raise ValueError('research full-notional trade bankrupt; no margin/liquidation model')
        # Half of the fixed round-trip cost is accrued on entry; the second
        # half on exit. Final trade returns equal production exactly.
        for t in range(tin, tout):
            eq[t - lo] = capital * (1 + side * (frame.close.iloc[t] / entry - 1) - cost / 2)
        before = capital
        capital *= 1 + ret
        eq[tout - lo:] = capital
        rows.append(dict(entry_date=frame.date.iloc[tin], exit_date=frame.date.iloc[tout], side=side,
                         entry=entry, exit=exit_, gross_return=gross, net_return=ret,
                         cost_amount=before * cost, ambiguous_entry_bar=bool(touched), tag=tr['tag']))
    daily_return = np.r_[eq[0] - 1, eq[1:] / eq[:-1] - 1]
    if not np.isfinite(eq).all() or (eq <= 0).any():
        raise ValueError('nonpositive intraperiod capital; research engine has no margin/liquidation model')
    peak = np.maximum.accumulate(np.r_[1., eq])
    drawdown = float(np.min(np.r_[1., eq] / peak - 1))
    stats = dict(net_return=float(capital - 1), max_drawdown=drawdown, trades=len(rows),
                 one_way_turnover=2 * len(rows), turnover_annualized=2 * len(rows) * 252 / len(eq),
                 cost_amount=sum(r['cost_amount'] for r in rows), both_band_bars=both_count,
                 ambiguous_entry_bars=ambiguous, gap_entries=entry_gap_count, test_bars=len(eq))
    daily = pd.DataFrame(dict(date=frame.date.iloc[lo:].to_numpy(), equity=eq, daily_return=daily_return))
    return stats, daily, rows


def run(panel, config):
    """Return auditable CSV-ready tables. No persisted current references are read."""
    config.validate()
    panel = {t: clean_frame(d) for t, d in panel.items()}
    folds = make_folds(panel, config)
    results, selections, audit, daily_rows, trade_rows, features = [], [], [], [], [], []
    for fold in folds:
        for kind in config.kinds:
            trains, tables, reference, reference_v2, coverage = training_snapshot(panel, fold, kind, config)
            audit.extend(coverage)
            if reference is None:
                continue
            feature = reference.copy().assign(fold=fold['fold'], kind=kind, feature_asof=fold['train_end'], feature_set='production')
            features.append(feature)
            if reference_v2 is not None:
                features.append(reference_v2.assign(fold=fold['fold'], kind=kind, feature_asof=fold['train_end'], feature_set='v2'))
            for ticker, train in trains.items():
                full = panel[ticker]
                test = full[(full.date >= fold['test_start']) & (full.date <= fold['test_end'])]
                if len(test) != config.test_bars or test.date.iloc[0] != fold['test_start'] or test.date.iloc[-1] != fold['test_end']:
                    audit.append(dict(fold=fold['fold'], kind=kind, ticker=ticker, stage='test', included=False,
                                      reason='incomplete test sessions; excluded from matched comparison'))
                    continue
                frame = pd.concat([train, test], ignore_index=True)
                for mode in config.window_modes:
                    picks = choose(train, tables[ticker], reference, reference_v2, ticker, kind, mode, config)
                    if config.include_v2 and not any(p['strategy'] == 'v2' and p['range'] == 'short2' for p in picks):
                        audit.append(dict(fold=fold['fold'], kind=kind, ticker=ticker, stage='v2_short2',
                                          window_mode=mode, included=False, reason='no ratio-separated second line'))
                    picks += [dict(strategy='fixed', range=f'ma{p}', period=p, train_sar_return=np.nan, candidate_periods='') for p in config.fixed_periods]
                    for pick in picks:
                        context = dict(fold=fold['fold'], ticker=ticker, kind=kind, window_mode=mode,
                                       strategy=pick['strategy'], range=pick['range'], period=pick['period'])
                        selections.append({**context, **fold, **pick, 'reference_n': len(trains),
                                           'reference_tickers': ' '.join(sorted(trains)), 'reference_asof': fold['train_end']})
                        cost = cost_of(ticker) * config.cost_multiplier
                        for scenario in config.scenarios:
                            ctx = dict(**context, scenario=scenario)
                            stats, daily, trades = replay(frame, pick['period'], kind, fold['test_start'], scenario, cost, config.slippage_bps)
                            results.append({**ctx, **fold, **stats, 'round_trip_cost': cost})
                            daily_rows.append(daily.assign(**ctx))
                            trade_rows.extend({**ctx, **trade} for trade in trades)
    return dict(folds=pd.DataFrame(folds), results=pd.DataFrame(results), selections=pd.DataFrame(selections),
                coverage=pd.DataFrame(audit), daily=pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame(),
                trades=pd.DataFrame(trade_rows), reference_features=pd.concat(features, ignore_index=True) if features else pd.DataFrame())


def summaries(tables):
    """Equal-weight daily rebalanced portfolio, matched complete-fold cohorts.

    Each fold starts flat and liquidates at its end; adjacent fold daily returns
    are compounded. Output periods include full OOS and each calendar year.
    """
    daily, results = tables['daily'], tables['results']
    if daily.empty:
        return pd.DataFrame(), pd.DataFrame()
    keys = ['kind', 'window_mode', 'strategy', 'range', 'scenario']
    portfolio = daily.groupby(keys + ['date'], as_index=False).agg(daily_return=('daily_return', 'mean'), ticker_count=('ticker', 'nunique'))
    out = []
    for group, d in portfolio.groupby(keys, sort=True):
        d = d.sort_values('date')
        subsets = [('all', d)] + [(str(y), g) for y, g in d.groupby(d.date.dt.year)]
        for period, sub in subsets:
            eq = np.r_[1., np.cumprod(1 + sub.daily_return.to_numpy())]
            out.append(dict(zip(keys, group)) | dict(report_period=period, sessions=len(sub),
                start=sub.date.min(), end=sub.date.max(), net_return=eq[-1] - 1,
                max_drawdown=float((eq / np.maximum.accumulate(eq) - 1).min()), min_tickers=int(sub.ticker_count.min())))
    turnover = results.groupby(keys, as_index=False).agg(mean_turnover_annualized=('turnover_annualized', 'mean'),
        trades=('trades', 'sum'), both_band_bars=('both_band_bars', 'sum'), ambiguous_entry_bars=('ambiguous_entry_bars', 'sum'),
        mean_fold_return=('net_return', 'mean'), mean_fold_drawdown=('max_drawdown', 'mean'), evaluated_ticker_folds=('fold', 'size'))
    return pd.DataFrame(out), turnover
