"""Tests for the pressure-based volume estimate (pressure_volume.py)."""
import pandas as pd
import pytest

from pressure_volume import (P_ATM_MBAR, bands, cooking_events, event_volumes, storage_constant, unit_ratios)


def _rows(minutes, flow, pressure):
    t0 = pd.Timestamp("2026-03-01T10:00Z")
    return pd.DataFrame({"timestamp": [t0 + pd.Timedelta(minutes=m) for m in minutes],
                         "flow_corrected": flow, "pressure": pressure})


def test_storage_constant_is_the_design_gas_store_per_metre_of_water():
    # modified CAMARTEC sizing table: gas store of 0.90 m3 in a plant of 3.90 m3
    assert [round(storage_constant(v), 1) for v in (8, 10, 12)] == [18.8, 23.5, 28.2]
    assert storage_constant(8, store_m3=3.0) == pytest.approx(3000 / 98.1)


def test_an_event_runs_from_the_first_to_the_last_row_with_flow():
    c = _rows(range(8), [0, 0, 5, 5, 5, 5, 0, 0], [60] * 8)
    ev = cooking_events(c)
    assert len(ev) == 1
    assert (ev.start[0], ev.end[0]) == (c.timestamp[2], c.timestamp[5])


def test_a_short_interruption_does_not_split_an_event_but_a_long_one_does():
    # rows without flow up to 3 min after the last row with flow keep the event open
    c = _rows([0, 1, 2, 3, 4, 5, 6, 7], [5, 5, 0, 0, 5, 5, 5, 5], [60] * 8)
    assert len(cooking_events(c)) == 1
    c = _rows([0, 1, 2, 3, 4, 6, 10, 11, 12, 13], [5, 5, 5, 0, 0, 0, 5, 5, 5, 5], [60] * 10)
    assert len(cooking_events(c)) == 2


def test_events_shorter_than_two_minutes_are_dropped():
    c = _rows(range(6), [0, 5, 5, 0, 0, 0], [60] * 6)
    assert cooking_events(c).empty


def test_event_volume_is_the_storage_constant_times_the_pressure_drop():
    # 80 mbar before, 70 mbar after: 10 mbar on a 12 m3 digester
    c = _rows(range(-3, 9), [0, 0, 0, 5, 5, 5, 5, 5, 0, 0, 0, 0],
              [80, 80, 80, 78, 76, 74, 72, 70, 70, 70, 70, 70])
    ev = event_volumes(c, 12)
    assert ev.drop_mbar.tolist() == [10.0]
    to_reference = (P_ATM_MBAR + 75) / P_ATM_MBAR * 293.15 / 298.15
    assert ev.volume_L[0] == pytest.approx(storage_constant(12) * 10 * to_reference)


def test_events_without_a_pressure_drop_are_not_counted():
    c = _rows(range(8), [0, 0, 5, 5, 5, 5, 0, 0], [60, 60, 60, 60, 60, 60, 59.8, 59.8])
    assert event_volumes(c, 12).empty


def test_unit_ratio_is_the_median_daily_ratio_on_days_with_both_volumes():
    days = pd.DataFrame({"unit": ["a"] * 4, "volume_L": [100.0, 200.0, 300.0, 50.0],
                         "pressure_L": [100.0, 100.0, 100.0, float("nan")]})
    assert unit_ratios(days).to_dict() == {"a": 2.0}


def test_bands_are_taken_around_the_median_so_the_assumed_store_does_not_move_them():
    r = pd.Series({"a": 0.5, "b": 0.9, "c": 1.0, "d": 1.1, "e": 2.0})
    split = {k: sorted(v.index) for k, v in bands(r).items()}
    assert split == {"within": ["b", "c", "d"], "lower": ["a"], "higher": ["e"]}
    assert {k: sorted(v.index) for k, v in bands(r * 0.8).items()} == split
