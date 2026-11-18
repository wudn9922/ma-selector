"""Focused app cache regressions. Run: python tests/test_app_cache.py"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_cache import calc_ref_bests, data_fingerprint, reference_key, ref_bests
from core import score, score_v2, standardize


class AppCacheTests(unittest.TestCase):
    def test_fingerprint_changes_with_prices_despite_equal_end_date_and_length(self):
        before = pd.DataFrame({'date': pd.date_range('2026-01-01', periods=8),
                               'open': np.arange(100., 108.), 'high': np.arange(102., 110.),
                               'low': np.arange(98., 106.), 'close': np.arange(101., 109.),
                               'volume': np.arange(1000., 1008.)})
        self.assertEqual(data_fingerprint(before), data_fingerprint(before.copy()))
        for column in before.columns:
            with self.subTest(column=column):
                changed = before.copy()
                changed.loc[3, column] += pd.Timedelta(hours=1) if column == 'date' else .25
                self.assertEqual(len(changed), len(before))
                self.assertEqual(changed.date.iloc[-1], before.date.iloc[-1])
                self.assertNotEqual(data_fingerprint(before), data_fingerprint(changed))

    def test_ref_bests_separates_us_and_tw_files_with_equal_mtime(self):
        ws_key = json.dumps(score.WS, sort_keys=True)
        calc_ref_bests.clear()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                for kind, us_name, tw_name, feats, compute in (
                    ('SMA', 'reference.parquet', 'reference_tw.parquet', score.FEATS, standardize.ref_stock_bests),
                    ('V2', 'reference_v2.parquet', 'reference_tw_v2.parquet', score_v2.FEATS_V2, standardize.ref_stock_bests_v2),
                ):
                    with self.subTest(kind=kind):
                        frames = [pd.DataFrame([{'ticker': f'{mkt}{t}', 'period': p,
                                                 **{f: float(t if mkt == 'US' else 2 - t) for f in feats}}
                                                for t in range(3) for p in range(15, 111)])
                                  for mkt in ('US', 'TW')]
                        paths = [Path(tmp) / name for name in (us_name, tw_name)]
                        for path, frame in zip(paths, frames):
                            frame.to_parquet(path)
                            os.utime(path, ns=(1_700_000_000_000_000_000,) * 2)
                        self.assertEqual(paths[0].stat().st_mtime_ns, paths[1].stat().st_mtime_ns)
                        self.assertNotEqual(reference_key(paths[0]), reference_key(paths[1]))
                        results = [ref_bests(kind, path, frame, score.WS, ws_key) for path, frame in zip(paths, frames)]
                        for actual, frame in zip(results, frames):
                            pd.testing.assert_frame_equal(actual, compute(frame, score.WS))
                        self.assertNotEqual(results[0].ticker.tolist(), results[1].ticker.tolist())
                        self.assertFalse(results[0].drop(columns='ticker').equals(results[1].drop(columns='ticker')))
                        # An update one nanosecond later must invalidate the same file's cache.
                        newer = frames[1].assign(ticker=lambda f: 'NEW_' + f.ticker)
                        old_key = reference_key(paths[1])
                        newer.to_parquet(paths[1])
                        os.utime(paths[1], ns=(1_700_000_000_000_000_001,) * 2)
                        self.assertNotEqual(old_key, reference_key(paths[1]))
                        pd.testing.assert_frame_equal(ref_bests(kind, paths[1], newer, score.WS, ws_key), compute(newer, score.WS))
        finally:
            calc_ref_bests.clear()


if __name__ == '__main__':
    unittest.main()
