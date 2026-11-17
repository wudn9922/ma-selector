"""Deterministic, offline tests for research boundaries and execution assumptions."""
from dataclasses import replace
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import data, events
from core.ma import moving_average
from experiments.walk_forward import engine


def synthetic(n=950, phase=0):
    t = np.arange(n)
    close = 100 + t * .025 + 9 * np.sin(t / 13 + phase) + 3 * np.sin(t / 4.1)
    open_ = np.r_[close[0], close[:-1]] + .4 * np.sin(t / 7)
    return data.normalize(pd.DataFrame(dict(time=pd.bdate_range('2022-01-03', periods=n), open=open_,
        high=np.maximum(open_, close) + 1.5, low=np.minimum(open_, close) - 1.5,
        close=close, volume=1_000_000 + t * 100)))


class WalkForwardTests(unittest.TestCase):
    def test_inputs_bounded(self):
        for kwargs in (dict(folds=13), dict(test_bars=20), dict(train_bars=800), dict(slippage_bps=51),
                       dict(cost_multiplier=-1), dict(fixed_periods=(14,)), dict(kinds=('SMA', 'SMA'))):
            with self.assertRaises(ValueError):
                replace(engine.Config(), **kwargs).validate()

    def test_disjoint_boundaries(self):
        panel = {'A': synthetic(1254), 'B': synthetic(1254, 1)}
        cfg = engine.Config(min_reference=2)
        folds = engine.make_folds(panel, cfg)
        self.assertEqual(len(folds), 4)
        for fold in folds:
            self.assertLess(fold['train_end'], fold['test_start'])
            self.assertEqual(len(panel['A'].query('date >= @fold["test_start"] and date <= @fold["test_end"]')), cfg.test_bars)
        for previous, current in zip(folds, folds[1:]):
            self.assertLess(previous['test_end'], current['test_start'])

    def test_market_pools_not_mixed(self):
        with self.assertRaisesRegex(ValueError, 'one market'):
            engine.make_folds({'A': synthetic(), '2330.TW': synthetic()}, engine.Config(min_reference=2))

    def test_no_partial_history_fold(self):
        with self.assertRaisesRegex(ValueError, 'no full test fold'):
            engine.make_folds({'A': synthetic(880), 'B': synthetic(880)}, engine.Config(min_reference=2))

    def test_past_only_features_and_selections(self):
        panel = {'A': synthetic(), 'B': synthetic(phase=1)}
        cfg = engine.Config(folds=1, test_bars=21, min_reference=2, window_modes=('mark_to_market',),
                            fixed_periods=(20,), scenarios=('current',), include_v2=True)
        fold = engine.make_folds(panel, cfg)[0]
        snapshot = engine.training_snapshot(panel, fold, 'SMA', cfg)
        changed = {t: frame.copy() for t, frame in panel.items()}
        for frame in changed.values():
            future = frame.date > fold['train_end']
            frame.loc[future, ['open', 'high', 'low', 'close']] *= 3
        other = engine.training_snapshot(changed, fold, 'SMA', cfg)
        pd.testing.assert_frame_equal(snapshot[2], other[2])
        pd.testing.assert_frame_equal(snapshot[3], other[3])
        self.assertTrue(all(frame.date.max() <= fold['train_end'] for frame in snapshot[0].values()))
        # The resulting production and v2 choices must also be invariant.
        for ticker in panel:
            a = engine.choose(snapshot[0][ticker], snapshot[1][ticker], snapshot[2], snapshot[3], ticker, 'SMA', 'mark_to_market', cfg)
            b = engine.choose(other[0][ticker], other[1][ticker], other[2], other[3], ticker, 'SMA', 'mark_to_market', cfg)
            self.assertEqual(a, b)

    def test_reference_kind_is_recomputed(self):
        panel = {'A': synthetic(), 'B': synthetic(phase=1)}
        cfg = engine.Config(folds=1, test_bars=21, min_reference=2)
        fold = engine.make_folds(panel, cfg)[0]
        sma = engine.training_snapshot(panel, fold, 'SMA', cfg)[2]
        ema = engine.training_snapshot(panel, fold, 'EMA', cfg)[2]
        self.assertFalse(sma.equals(ema))

    def test_current_replays_independent_production_ledger(self):
        frame = synthetic(220)
        start, cost = frame.date.iloc[150], .001
        args = [frame[c].to_numpy(float) for c in ('open', 'high', 'low', 'close')]
        ma = moving_average(frame.close, 20)
        atr = data.wilder_atr(frame).copy()
        atr[:150] = np.nan
        trades = events.events(*args, ma, atr, cost=cost)[4]
        expected = np.prod([1 + tr[3] for tr in trades]) - 1
        stats, daily, rows = engine.replay(frame, 20, 'SMA', start, cost=cost)
        self.assertGreater(len(trades), 0)
        self.assertAlmostEqual(stats['net_return'], expected, places=12)
        self.assertAlmostEqual(daily.equity.iloc[-1] - 1, expected, places=12)
        self.assertEqual(len(rows), len(trades))
        for row, trade in zip(rows, trades):
            self.assertAlmostEqual(row['net_return'], trade[3], places=12)
            self.assertGreaterEqual(row['entry_date'], start)

    def test_same_bar_stress_and_turnover(self):
        frame = synthetic(64)
        frame.loc[:, ['open', 'high', 'low', 'close']] = [100., 104., 96., 102.]
        start = frame.date.iloc[30]
        with patch.object(engine, 'moving_average', return_value=np.full(len(frame), 100.)):
            cur, _, current = engine.replay(frame, 20, 'SMA', start)
            con, _, conservative = engine.replay(frame, 20, 'SMA', start, 'conservative', slippage_bps=5)
            opt, _, optimistic = engine.replay(frame, 20, 'SMA', start, 'optimistic')
        self.assertGreater(cur['ambiguous_entry_bars'], 0)
        self.assertEqual(cur['both_band_bars'], 34)
        self.assertEqual(cur['trades'], con['trades'])
        self.assertEqual(cur['one_way_turnover'], 2 * cur['trades'])
        self.assertTrue(all(t['entry_date'] == t['exit_date'] for t in conservative))
        self.assertLess(conservative[0]['net_return'], current[0]['net_return'])
        self.assertEqual(len(current), len(optimistic))

    def test_zero_cost_has_higher_return_for_same_schedule(self):
        frame = synthetic(220)
        a, _, _ = engine.replay(frame, 20, 'SMA', frame.date.iloc[150], cost=0)
        b, _, _ = engine.replay(frame, 20, 'SMA', frame.date.iloc[150], cost=.01)
        self.assertEqual(a['trades'], b['trades'])
        self.assertGreater(a['net_return'], b['net_return'])

    def test_execution_prefix_does_not_change_with_future_prices(self):
        frame = synthetic(220)
        _, a, _ = engine.replay(frame, 20, 'SMA', frame.date.iloc[150])
        # Keep this causality test inside the engine's positive-capital domain.
        for factor in (.75, 1.25):
            changed = frame.copy()
            changed.loc[200:, ['open', 'high', 'low', 'close']] *= factor
            _, b, _ = engine.replay(changed, 20, 'SMA', frame.date.iloc[150])
            pd.testing.assert_frame_equal(a[a.date < frame.date.iloc[200]], b[b.date < frame.date.iloc[200]])

    def test_bankruptcy_is_rejected_instead_of_publishing_negative_equity(self):
        frame = synthetic(220)
        frame.loc[200:, ['open', 'high', 'low', 'close']] *= 3
        with self.assertRaisesRegex(ValueError, 'bankrupt|nonpositive'):
            engine.replay(frame, 20, 'SMA', frame.date.iloc[150])

    def test_portfolio_and_calendar_period_summary(self):
        context = dict(kind='SMA', window_mode='mark_to_market', strategy='fixed', range='ma20', scenario='current')
        daily = pd.DataFrame([{**context, 'ticker': t, 'date': pd.Timestamp(d), 'daily_return': r}
            for t, d, r in [('A', '2025-12-31', .1), ('B', '2025-12-31', -.1),
                             ('A', '2026-01-02', .2), ('B', '2026-01-02', 0.)]])
        result = pd.DataFrame([{**context, 'turnover_annualized': 12., 'trades': 2, 'both_band_bars': 1,
            'ambiguous_entry_bars': 0, 'net_return': .1, 'max_drawdown': -.05, 'fold': 1}])
        summary, turnover = engine.summaries(dict(daily=daily, results=result))
        self.assertAlmostEqual(summary.query('report_period == "all"').net_return.iloc[0], .1)
        self.assertAlmostEqual(summary.query('report_period == "2025"').net_return.iloc[0], 0.)
        self.assertEqual(summary.min_tickers.min(), 2)
        self.assertEqual(turnover.trades.iloc[0], 2)

    def test_drawdown_includes_initial_capital(self):
        frame = synthetic(64)
        frame.loc[:, ['open', 'high', 'low', 'close']] = [100., 102., 99., 100.]
        with patch.object(engine, 'moving_average', return_value=np.full(len(frame), 100.)):
            stats, daily, _ = engine.replay(frame, 20, 'SMA', frame.date.iloc[30])
        self.assertLess(stats['max_drawdown'], 0)
        self.assertEqual(stats['max_drawdown'], daily.equity.min() - 1)


if __name__ == '__main__':
    unittest.main()
