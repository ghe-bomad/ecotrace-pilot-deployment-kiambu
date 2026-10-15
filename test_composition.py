"""Tests for the reference gas-composition table behind Figure 5."""
import math

import pytest

import make_figures
from make_figures import composition_table, fig_composition, set_mpl, H2S_RANGE_PPM


RAW = {
    "01001": [  # measured before and after the H2S filter
        {"CO2_vol_perc": 43.0, "CH4_vol_perc": 51, "O2_vol_perc": 0, "H2S_ppm": 66.5, "CO_ppm": 3,
         "NH3_ppm": 228, "after_H2S_removal": "False"},
        {"CO2_vol_perc": 37.0, "CH4_vol_perc": 48.5, "O2_vol_perc": 0, "H2S_ppm": 43.8, "CO_ppm": 5,
         "NH3_ppm": 136, "after_H2S_removal": "True"}],
    "01002": [  # saturated readings
        {"CO2_vol_perc": 38.5, "CH4_vol_perc": 52, "O2_vol_perc": 0, "H2S_ppm": "max", "CO_ppm": 6,
         "NH3_ppm": "max", "after_H2S_removal": "False"}],
    "01004": [  # only measured after the filter
        {"CO2_vol_perc": 38.0, "CH4_vol_perc": 55, "O2_vol_perc": 0, "H2S_ppm": 21.8, "CO_ppm": 2,
         "NH3_ppm": 74, "after_H2S_removal": "True"}],
    "01005": [  # ILRI research reactor: out of scope
        {"CO2_vol_perc": 40.0, "CH4_vol_perc": 52, "O2_vol_perc": 0, "H2S_ppm": "max", "CO_ppm": 15,
         "NH3_ppm": "max", "after_H2S_removal": "True"}],
    "pig_dung": [  # no sensor installed: out of scope
        {"CO2_vol_perc": 40.0, "CH4_vol_perc": 52, "O2_vol_perc": -0.4, "H2S_ppm": "max", "CO_ppm": 0,
         "NH3_ppm": "max", "after_H2S_removal": "False"}],
}


def test_only_household_units_are_kept():
    t = composition_table(RAW)
    assert list(t["unit"]) == ["01001", "01002", "01004"]


def test_main_composition_comes_from_the_raw_gas_reading():
    t = composition_table(RAW).set_index("unit")
    assert t.loc["01001", "CH4"] == 51 and t.loc["01001", "CO2"] == 43.0


def test_h2s_before_and_after_the_filter_are_kept_apart():
    t = composition_table(RAW).set_index("unit")
    assert t.loc["01001", "H2S_raw"] == 66.5 and t.loc["01001", "H2S_filtered"] == 43.8
    assert math.isnan(t.loc["01002", "H2S_filtered"])


def test_unit_measured_only_after_the_filter():
    t = composition_table(RAW).set_index("unit")
    assert t.loc["01004", "CH4"] == 55
    assert math.isnan(t.loc["01004", "H2S_raw"]) and t.loc["01004", "H2S_filtered"] == 21.8


def test_saturated_readings_sit_at_the_range_limit_and_are_flagged():
    t = composition_table(RAW).set_index("unit")
    assert t.loc["01002", "H2S_raw"] == H2S_RANGE_PPM and t.loc["01002", "H2S_raw_sat"]
    assert not t.loc["01001", "H2S_raw_sat"]


def test_co_and_ammonia_are_not_reported():
    # CO read near zero and NH3 is not discussed in the paper
    assert list(composition_table(RAW).columns) == [
        "unit", "CH4", "CO2", "O2", "H2S_raw", "H2S_raw_sat", "H2S_filtered", "H2S_filtered_sat"]


def test_fig_composition_writes_figure_5(tmp_path, monkeypatch):
    monkeypatch.setattr(make_figures, "OUT", tmp_path)
    set_mpl()
    fig_composition(composition_table(RAW))
    assert (tmp_path / "Figure_5.png").stat().st_size > 0
    assert (tmp_path / "Figure_5.pdf").stat().st_size > 0


def test_h2s_before_and_after_sit_on_one_vertical_joined_by_an_arrow(tmp_path, monkeypatch):
    monkeypatch.setattr(make_figures, "OUT", tmp_path)
    set_mpl()
    t = composition_table(RAW)
    fig = fig_composition(t)
    ax = fig.axes[1]
    lines = {ln.get_gid(): ln for ln in ax.lines if ln.get_gid()}
    assert list(lines["H2S_raw"].get_xdata()) == list(lines["H2S_filtered"].get_xdata())
    # only 01001 (x = 0) was measured before and after the filter: one arrow, top to bottom
    from matplotlib.text import Annotation
    arrows = [a for a in ax.texts if isinstance(a, Annotation)]
    assert len(arrows) == 1
    assert arrows[0].xyann == (0, 66.5) and arrows[0].xy == (0, 43.8)
