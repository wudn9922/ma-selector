"""Window equity is an account value ratio; executions retain original entry basis."""
import sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import backtest as bt, select as sel, select_v2, recommend


def bars():
    C = np.array([98., 98., 102., 110., 110., 110.])
    O = C.copy(); O[2] = 101.
    H, L = C + .5, C - .5; H[2], L[2] = 102.5, 100.5
    return O, H, L, C, np.ones(6), np.full(6, 100.), np.ones(6)


def sar(a, lo, **kw):
    O, H, L, C, V, ma, atr = a
    return sel.sar_stats(O, H, L, C, atr, ma, lo, **kw)


def test_carried_long_counts_only_window_and_preserves_execution():
    a = bars()
    new, nt, eq = bt.run(*a, lo=4, cost=0., retest=False, return_eq=True)
    old, ot = bt.run(*a, lo=4, cost=0., retest=False, window_mode='legacy_exit')
    assert new['總報酬'] == pytest.approx(0.)
    assert old['總報酬'] == pytest.approx(110 / 101 - 1)
    assert [(t['tin'], t['tout'], t['side']) for t in nt] == [(t['tin'], t['tout'], t['side']) for t in ot] == [(2, 5, 1)]
    np.testing.assert_allclose(eq, 1.)
    assert sar(a, 4, cost=0.)['報酬'] == pytest.approx(0.)
    assert sar(a, 4, cost=0., window_mode='legacy_exit')['報酬'] == pytest.approx(110 / 101 - 1)


def test_short_preserves_units_instead_of_releveraging_at_boundary():
    a = bars(); O, H, L, C, V, ma, atr = a
    C[:] = [110, 110, 97, 90, 85, 80]; O[:] = C; O[2] = 98
    H[:] = np.maximum(O, C) + .5; L[:] = np.minimum(O, C) - .5
    expected = (2 - 80 / 98) / (2 - 90 / 98) - 1
    st, tr = bt.run(*a, lo=4, cost=0., retest=False, longonly=False)
    assert st['總報酬'] == pytest.approx(expected)
    assert sar(a, 4, cost=0.)['報酬'] == pytest.approx(expected)
    assert expected != pytest.approx(-(80 / 90 - 1))
    assert tr[0]['side'] == -1


def test_complex_pre_window_partial_proceeds_are_cash_and_stop_uses_actual_entry():
    a = bars(); O, H, L, C, *_ = a
    O[4:] = 100.; C[4:] = 100.; H[4:] = 100.5; L[4:] = 99.5
    cost = .002
    kw = dict(lo=4, mode='complex', retest=False, ex_day2=False, surge_pct=1., surge_atr=1000., cost=cost)
    new, tr, eq = bt.run(*a, return_eq=True, **kw)
    old, old_tr = bt.run(*a, window_mode='legacy_exit', **kw)
    # Half sold at entry*1.03 before lo. Remainder stops at actual entry 101.
    boundary = 1 + .5 * (.03 - cost) + .5 * (110 / 101 - 1)
    final = 1 + .5 * (.03 - cost) - .5 * cost
    assert new['總報酬'] == pytest.approx(final / boundary - 1)
    assert tr[0]['tout'] == old_tr[0]['tout'] == 4
    assert old['總報酬'] == pytest.approx(final - 1)
    assert eq[-1] == pytest.approx(1 + new['總報酬'])
    assert new['最大回撤'] == pytest.approx(new['總報酬'])


def test_complex_partial_exit_inside_window_counts_only_incremental_pnl():
    a = bars(); O, H, L, C, *_ = a
    O[4] = C[4] = 120.; H[4] = 120.5; L[4] = 119.5
    O[5] = C[5] = 101.; H[5] = 101.5; L[5] = 100.5
    cost = .002
    st, tr = bt.run(*a, lo=4, mode='complex', retest=False, ex_day2=False, surge_pct=.05, surge_atr=1000., cost=cost)
    # Day 3 also surges: .5 TP + .1 surge precede lo; .1 surge on day 4.
    boundary = 1 + .5 * (.03 - cost) + .1 * (110 / 101 - 1 - cost) + .4 * (110 / 101 - 1)
    final = 1 + .5 * (.03 - cost) + .1 * (110 / 101 - 1 - cost) + .1 * (120 / 101 - 1 - cost) - .3 * cost
    assert st['總報酬'] == pytest.approx(final / boundary - 1)
    assert len(tr) == 1


def test_complex_pre_window_half_stop_retains_cash_and_remaining_units():
    a = bars(); O, H, L, C, *_ = a
    O[4], C[4], H[4], L[4] = 100., 99., 100.5, 98.
    O[5], C[5], H[5], L[5] = 105., 105., 105.5, 104.5
    cost = .002
    kw = dict(lo=5, mode='complex', retest=False, ex_day2=False, tp=1., cost=cost)
    st, tr = bt.run(*a, **kw)
    old, old_tr = bt.run(*a, window_mode='legacy_exit', **kw)
    cash_pnl = .5 * (98.5 / 101 - 1 - cost)
    boundary = 1 + cash_pnl + .5 * (99 / 101 - 1)
    final = 1 + cash_pnl + .5 * (105 / 101 - 1 - cost)
    assert st['總報酬'] == pytest.approx(final / boundary - 1)
    assert old['總報酬'] == pytest.approx(final - 1)
    assert [(t['tin'], t['tout'], t.get('open')) for t in tr] == [(t['tin'], t['tout'], t.get('open')) for t in old_tr]


def test_complex_carried_short_partial_cash_uses_original_entry_units():
    a = bars(); O, H, L, C, V, ma, atr = a
    C[:] = [110, 110, 97, 90, 85, 80]; O[:] = C; O[2] = 98
    H[:] = np.maximum(O, C) + .5; L[:] = np.minimum(O, C) - .5
    cost = .002
    st, tr = bt.run(*a, lo=4, mode='complex', retest=False, longonly=False,
                    ex_day2=False, surge_pct=1., surge_atr=1000., cost=cost)
    # Half took profit at 98*.97 before lo; cash is no longer short exposure.
    boundary = 1 + .5 * (.03 - cost) + .5 * (1 - 90 / 98)
    final = 1 + .5 * (.03 - cost) + .5 * (1 - 80 / 98 - cost)
    assert st['總報酬'] == pytest.approx(final / boundary - 1)
    assert tr[0]['side'] == -1


def test_exit_on_first_window_day_includes_gap_and_cost():
    a = bars(); O, H, L, C, *_ = a
    O[4:] = C[4:] = 97.; H[4:] = 97.5; L[4:] = 96.5
    st, tr, eq = bt.run(*a, lo=4, cost=.001, retest=False, return_eq=True)
    expected = (97 / 101 - .001) / (110 / 101) - 1
    assert st['總報酬'] == pytest.approx(expected)
    assert st['最大回撤'] == pytest.approx(expected)
    assert tr[0]['tout'] == 4
    assert eq[4] == pytest.approx(1 + expected)


def test_final_cost_is_in_equity_and_drawdown():
    a = bars()
    st, tr, eq = bt.run(*a, lo=5, cost=.01, retest=False, return_eq=True)
    expected = -.01 / (110 / 101)
    assert st['總報酬'] == pytest.approx(expected)
    assert st['最大回撤'] == pytest.approx(expected)
    assert eq[-1] == pytest.approx(1 + expected)
    assert sar(a, 5, cost=.01)['回撤'] == pytest.approx(expected)


def test_window_start_entry_is_not_marked_from_previous_close():
    a = bars()
    st, tr = bt.run(*a, lo=2, cost=0., retest=False)
    assert st['總報酬'] == pytest.approx(110 / 101 - 1)
    a[-1][1] = np.nan  # No preceding SAR short; the first signal is on lo.
    assert sar(a, 2, cost=0.)['報酬'] == pytest.approx(110 / 101 - 1)


def test_missing_indicator_skips_execution_but_still_marks_held_equity():
    a = bars(); O, H, L, C, V, ma, atr = a
    C[4] = O[4] = 105.; H[4], L[4] = 105.5, 104.5
    atr[4] = np.nan
    st, tr, eq = bt.run(*a, lo=4, retest=False, cost=0., return_eq=True)
    assert eq[4] == pytest.approx(105 / 110)
    assert st['最大回撤'] == pytest.approx(105 / 110 - 1)
    assert st['總報酬'] == pytest.approx(0.)
    assert (tr[0]['tin'], tr[0]['tout']) == (2, 5)


def test_sar_zero_equity_is_absorbing_legacy_negative_compounding_unchanged():
    a = bars()
    trades = [(2, 3, -1, -1.5, 'B'), (4, 5, -1, -1.5, 'B')]
    with patch.object(sel.ev, 'events', return_value=([], [], [], [], trades)):
        new = sar(a, 0); old = sar(a, 0, window_mode='legacy_exit')
    assert new['報酬'] == new['回撤'] == -1.
    assert new['筆數'] == 1
    assert old['報酬'] == -.75


@pytest.mark.parametrize('missing_indicator', [False, True])
def test_backtest_gap_bankruptcy_cannot_recover(missing_indicator):
    a = bars(); O, H, L, C, V, ma, atr = a
    C[:] = [110, 110, 97, 250, 98, 250]; O[:] = C; O[2] = 98
    H[:] = np.maximum(O, C) + .5; L[:] = np.minimum(O, C) - .5
    if missing_indicator: atr[3] = np.nan
    st, tr, eq = bt.run(*a, lo=2, cost=0., retest=False, longonly=False, return_eq=True)
    assert st['總報酬'] == st['最大回撤'] == -1.
    assert tr[0]['ret'] == -1.
    np.testing.assert_array_equal(eq[3:], 0.)


def test_v2_propagates_explicit_window_mode():
    assert select_v2.select_v2.__defaults__[-1] == sel.WINDOW_MODE
    assert recommend.scoring_id() == 'period+range+mark_to_market'
    assert recommend.scoring_id('legacy_exit') == 'period+range+legacy_exit'


@pytest.mark.parametrize('mode', ['bad', None])
def test_invalid_window_mode(mode):
    with pytest.raises(ValueError): bt.run(*bars(), window_mode=mode)
    with pytest.raises(ValueError): sar(bars(), 0, window_mode=mode)
    with pytest.raises(ValueError): sel.select(None, None, window_mode=mode)
    with pytest.raises(ValueError): select_v2.select_v2(None, None, None, window_mode=mode)
    with pytest.raises(ValueError): recommend.recommend(None, None, 'TEST', window_mode=mode)


@pytest.mark.parametrize('mode', ['simple', 'complex'])
@pytest.mark.parametrize('longonly', [True, False])
@pytest.mark.parametrize('entry_mode', bt.ENTRY_MODES)
@pytest.mark.parametrize('seed', [3, 29])
def test_window_equity_equals_full_account_rebased_without_signal_changes(mode, longonly, entry_mode, seed):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from regression_synth import synth
    from core import data
    df = data.normalize(synth(seed, 400))
    a = [df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close', 'volume')]
    a.extend([df.close.rolling(20).mean().to_numpy(), data.wilder_atr(df)])
    kw = dict(mode=mode, longonly=longonly, entry_mode=entry_mode, return_eq=True, ex_day2=False)
    full, full_trades, full_eq = bt.run(*a, **kw)
    for lo in (100, 237, 399):
        st, tr, eq = bt.run(*a, lo=lo, **kw)
        expected = full_eq[lo:] / full_eq[lo - 1]
        np.testing.assert_allclose(eq[lo:], expected, rtol=1e-12, atol=1e-12)
        assert st['總報酬'] == pytest.approx(expected[-1] - 1)
        seg = np.r_[1., expected]
        assert st['最大回撤'] == pytest.approx((seg / np.maximum.accumulate(seg) - 1).min())
        keys = lambda ts: [(t['tin'], t['tout'], t['side'], t['kind']) for t in ts]
        assert keys(tr) == keys([t for t in full_trades if t['tout'] >= lo])


@pytest.mark.parametrize('seed', [3, 29])
def test_sar_window_matches_independent_share_and_cash_ledger(seed):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from regression_synth import synth
    from core import data
    df = data.normalize(synth(seed, 400))
    O, H, L, C = [df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')]
    ma = df.close.rolling(20).mean().to_numpy(); atr = data.wilder_atr(df)
    *_, plog, trades = sel.ev.events(O, H, L, C, ma, atr, cost=.002)
    entry = {(tin, tout, side): price for tin, tout, side, price, _, _ in plog}
    equity = np.ones(len(C)); capital = 1.
    for tin, tout, side, ret, _ in trades:
        price = entry.get((tin, tout, side))
        if price is not None:
            shares = side * capital / price
            cash = capital - shares * price
            equity[tin:tout] = cash + shares * C[tin:tout]
        capital *= 1 + ret
        equity[tout:] = capital
    carried = next(tin + 1 for tin, tout, *_ in trades if tout - tin > 2)
    for lo in (0, 100, 237, 399, carried):
        stats = sel.sar_stats(O, H, L, C, atr, ma, lo, cost=.002)
        marked = equity[lo:] / (equity[lo - 1] if lo else 1.)
        seg = np.r_[1., marked]
        assert stats['報酬'] == pytest.approx(marked[-1] - 1, abs=1e-12)
        assert stats['回撤'] == pytest.approx((seg / np.maximum.accumulate(seg) - 1).min(), abs=1e-12)
        assert stats['筆數'] == len([t for t in trades if t[1] >= lo])


@pytest.mark.parametrize('window_mode', sel.WINDOW_MODES)
def test_primary_select_passes_accounting_to_simple_complex_and_sar(window_mode):
    import pandas as pd
    a = bars()
    df = pd.DataFrame(dict(zip(('open', 'high', 'low', 'close', 'volume'), a[:5])))
    scores = pd.DataFrame({'period': np.arange(15, 111), '分數': np.ones(96)})
    calls = []
    def backtest(*args, **kwargs):
        calls.append((kwargs['mode'], kwargs.get('window_mode', sel.WINDOW_MODE)))
        return dict(總報酬=.1, 最大回撤=-.1), []
    def stats(*args, **kwargs):
        calls.append(('sar', kwargs.get('window_mode', sel.WINDOW_MODE)))
        return dict(報酬=.1, 回撤=-.1, 勝率=.5, 筆數=2)
    with patch.object(bt, 'run', side_effect=backtest), patch.object(sel, 'sar_stats', side_effect=stats):
        result = sel.select(df, scores, window_mode=window_mode)
    assert {mode for mode, _ in calls} == {'simple', 'complex', 'sar'}
    assert {mode for _, mode in calls} == {window_mode}
    assert set(result) == {'短期', '中期', '長期'}


@pytest.mark.parametrize('window_mode', sel.WINDOW_MODES)
def test_select_v2_passes_accounting_to_every_primary_and_reference_window(window_mode):
    import pandas as pd
    a = bars()
    df = pd.DataFrame(dict(zip(('open', 'high', 'low', 'close', 'volume'), a[:5])))
    scores = pd.DataFrame({'period': np.arange(15, 111), **{f'分數_{y}': np.ones(96) for y in ('1y', '2y', '3y')}})
    calls = []
    def stats(*args, **kwargs):
        calls.append(kwargs.get('window_mode', sel.WINDOW_MODE))
        return dict(報酬=.1, 回撤=-.1, 勝率=.5, 筆數=2)
    with patch.object(select_v2, 'score_table_v2', return_value=scores), patch.object(sel, 'sar_stats', side_effect=stats):
        result = select_v2.select_v2(df, None, None, window_mode=window_mode)
    assert len(calls) >= 15
    assert set(calls) == {window_mode}
    assert result['短期']['cands'] and result['中期']['cands']
