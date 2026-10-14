"""Tests for the daily-volume calculation behind Figure 4."""
import pandas as pd
import pytest

from make_figures import PILOT_END, daily_volume


def _rows(times, flow, fill=None):
    return pd.DataFrame({"timestamp": pd.to_datetime(times, utc=True), "flow_zero_cal": flow,
                         "gap_fill_L": [0.0] * len(flow) if fill is None else fill})


def test_daily_volume_adds_the_gap_fill():
    # measured minutes plus the litres the dataset filled into a sleep during use
    c = _rows(["2026-03-01T10:00Z", "2026-03-01T10:05Z"], [6.0, 6.0], fill=[0.0, 24.0])
    assert daily_volume(c).sum() == 6.0 + 6.0 + 24.0


def test_daily_volume_counts_fill_on_idle_rows_too():
    # gap_fill_L sits on the row after the sleep; that row's own flow may be below the idle gate
    c = _rows(["2026-03-01T10:00Z", "2026-03-01T10:05Z"], [6.0, 0.3], fill=[0.0, 5.0])
    assert daily_volume(c).sum() == 6.0 + 5.0


def test_daily_volume_sums_litres_per_utc_day():
    # one-minute rows, so each L/min value is a litre count
    c = _rows(["2026-03-01T23:58Z", "2026-03-01T23:59Z", "2026-03-02T00:00Z"], [5.0, 3.0, 2.0])
    v = daily_volume(c)
    assert v.to_dict() == {pd.Timestamp("2026-03-01").date(): 8.0,
                           pd.Timestamp("2026-03-02").date(): 2.0}


def test_daily_volume_ignores_rows_after_pilot_end():
    after = PILOT_END + pd.Timedelta(minutes=5)
    c = _rows([PILOT_END - pd.Timedelta(minutes=1), after], [4.0, 9.0])
    assert daily_volume(c).sum() == 4.0


def test_daily_volume_ignores_idle_rows_below_the_no_flow_gate():
    # a zero-calibrated unit at its zero still reads ~0.02 L/min; that is not gas use
    c = _rows(["2026-03-01T10:00Z", "2026-03-01T10:01Z", "2026-03-01T10:02Z"], [5.0, 0.03, 2.0])
    assert daily_volume(c).sum() == 7.0
