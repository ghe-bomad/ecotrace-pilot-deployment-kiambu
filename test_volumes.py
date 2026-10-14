"""Tests for the daily-volume and missed-start calculations (Figure 4)."""
import pandas as pd
import pytest

from make_figures import PILOT_END, daily_volume
from make_stats import missed_litres


def _rows(times, flow):
    return pd.DataFrame({"timestamp": pd.to_datetime(times, utc=True), "flow_zero_cal": flow})


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


def test_missed_start_counts_wake_ups_into_flowing_gas():
    t0 = pd.Timestamp("2026-03-01T12:00Z")
    c = _rows([t0, t0 + pd.Timedelta(seconds=300), t0 + pd.Timedelta(seconds=360)], [0.0, 6.0, 6.0])
    # 300 s gap; each row already stands for its own minute, so 240 s are unmeasured,
    # and a start falls on average halfway through them: 120 s at 6 L/min
    assert missed_litres(c) == pytest.approx({"start": 12.0, "during": 0.0})


def test_sleep_during_use_loses_the_unmeasured_part_of_the_gap():
    t0 = pd.Timestamp("2026-03-01T12:00Z")
    c = _rows([t0, t0 + pd.Timedelta(seconds=300)], [8.0, 6.0])
    # gas flowed before and after the sleep: the 240 s not covered by either row's minute
    assert missed_litres(c) == pytest.approx({"start": 0.0, "during": 24.0})


def test_missed_start_ignores_wake_ups_without_flow_and_long_gaps():
    t0 = pd.Timestamp("2026-03-01T12:00Z")
    c = _rows([t0,
               t0 + pd.Timedelta(seconds=300),        # wake-up, no gas
               t0 + pd.Timedelta(hours=3)],           # data gap, not a sleep cycle
              [0.0, 0.5, 6.0])
    assert missed_litres(c) == {"start": 0.0, "during": 0.0}
