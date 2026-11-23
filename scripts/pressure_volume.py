"""Pressure-based gas volume and its comparison with the thermal volume.

The paper compares the reported (thermal) daily gas volumes with a second
estimate that takes the volume from the gas pressure the same units logged.

Principle. A fixed-dome digester stores gas under a rigid dome. Stored gas
pushes slurry into the compensation chamber, and the gauge pressure equals the
head between the two slurry levels, so the pressure rises as the store fills.
The estimate assumes that the stored gas volume is proportional to the gauge
pressure: the store is empty at zero pressure and holds STORE_FRACTION of the
nominal digester volume at P_FULL_MBAR. The storage constant is their ratio,

    C = STORE_FRACTION * nominal volume / P_FULL_MBAR     [L of gas per mbar],

18.8, 23.5 and 28.2 L/mbar for digesters of 8, 10 and 12 m3. C was not measured,
and the design of the pilot digesters is not documented, so both numbers come
from the literature on the East African dome designs:

- STORE_FRACTION. The sizing table of the modified CAMARTEC design gives a gas
  store of 0.90, 1.35, 2.03 and 3.04 m3 for a total plant volume of 3.9, 5.85,
  8.78 and 13.16 m3, 23 % in every size (Ng'wandu, Shila and ter Heegde,
  Programme Implementation Document, Tanzania Domestic Biogas Programme, 2009).
  The design drawings state the same share (Bos and Kombe, Mission Report on
  Design Selection of Domestic Biogas Plant for the Uganda Domestic Biogas
  Programme, SNV, 2009). The masonry domes of the Kenyan programme are
  described as similar to this design (Chaney et al., Energy Sustain. Dev. 86
  (2025) 101668).
- P_FULL_MBAR. 1 m water column is the upper limit of the gas pressure in the
  CAMARTEC design (Sasse, Kellner and Kimaro, Improved Biogas Unit for
  Developing Countries, Vieweg, 1991). Other sources give 80 mbar and above as
  the venting pressure (Robinson et al., Energy Res. Soc. Sci. 121 (2025)
  103963) and 0-120 mbar as the operating range (Chaney, Robinson and Clifford,
  Energy Sustain. Dev. 89 (2025) 101815).

Every ratio below is inversely proportional to STORE_FRACTION and proportional
to P_FULL_MBAR. main() prints the median ratio for 80 and 120 mbar. The
comparison therefore bounds the fleet-level volume only roughly; what it shows
independently of both numbers is how much the units differ from each other.

Per cooking event the gas withdrawn is C times the pressure drop:

- a cooking event is a period with corrected flow at or above EVENT_FLOW_MIN that
  lasts at least EVENT_MIN_MIN; rows below the threshold end it once they come
  more than EVENT_GAP_MIN after the last row above it. The flow only times the
  events; it does not enter the volume;
- the pressure drop is the highest pressure in the PRE_MIN minutes before the
  event minus the lowest pressure in the POST_MIN minutes after it; events with
  a drop of DROP_MIN mbar or less are not counted;
- the volume is converted from the digester (mean event pressure, T_DOME_C) to
  the paper's reference conditions (20 degC, 101.325 kPa) and summed per UTC
  day, by the start of the event.

Comparison. On each valid day of a usable unit (validity.py) with both volumes
above zero, the ratio is the thermal volume (make_figures.daily_volumes)
divided by the pressure-based volume. A unit's ratio is the median over its
days. Two groups of units have no pressure-based volume: units whose pressure
follows a manually closed valve and not the gas store (VALVE_UNITS), and the
unit whose pressure sensor is impaired (PRESSURE_FAULT_UNITS: the pressure of
01017 stays below 14 mbar on 99 % of its records, against 42 to 102 mbar on
the other units).

    python3 scripts/pressure_volume.py      # prints the numbers quoted in the paper

The event detection and the pressure drop follow the technical paper's
``plotting/pressure_balance.py``; here the result is reduced to the daily
volumes and the few numbers this paper quotes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from make_figures import DATA_REPO, FAILED, NOT_HOUSEHOLD, PILOT_END, corrected, daily_volumes

STORE_FRACTION = 0.90 / 3.90   # full gas store as a share of the nominal plant volume (modified CAMARTEC sizing table)
P_FULL_MBAR = 98.1        # pressure of the full store: 1.0 m water column
P_FULL_RANGE_MBAR = (80.0, 120.0)   # range of the full-store pressure in the literature
EVENT_FLOW_MIN = 0.5      # L/min, corrected flow that counts as gas in use
EVENT_MIN_MIN = 2.0       # shortest event
EVENT_GAP_MIN = 3.0       # a row below the threshold this long after the last row above it ends the event
PRE_MIN = 30              # window before the event for the highest pressure
POST_MIN = 5              # window after the event for the lowest pressure
DROP_MIN = 0.5            # mbar; smaller drops are not counted
P_ATM_MBAR = 1013.25
T_DOME_C = 25.0           # assumed gas temperature in the digester
T_REF_C = 20.0            # reference temperature of the paper's volumes
VALVE_UNITS = {"SN_01003", "SN_01008", "SN_01014"}
PRESSURE_FAULT_UNITS = {"SN_01017"}     # impaired pressure sensor, see the module docstring
BAND = 0.20               # a unit ratio within 1 +/- BAND counts as agreeing


def storage_constant(nominal_m3: float, store_m3: float | None = None) -> float:
    """Litres of stored gas per mbar of gauge pressure for one digester.

    ``store_m3`` replaces the assumed full store (STORE_FRACTION of the nominal volume).
    """
    store_m3 = STORE_FRACTION * nominal_m3 if store_m3 is None else store_m3
    return store_m3 * 1000.0 / P_FULL_MBAR


def cooking_events(c: pd.DataFrame) -> pd.DataFrame:
    """Start and end of every cooking event in one unit's measuring rows."""
    s = c.dropna(subset=["flow_corrected"]).sort_values("timestamp")
    above = (s["flow_corrected"] >= EVENT_FLOW_MIN).to_numpy()
    t = s["timestamp"]
    since_above = (t - t.where(above).ffill()) / pd.Timedelta(minutes=1)
    closes = ~above & (since_above > EVENT_GAP_MIN).to_numpy()
    event = np.cumsum(closes)[above]
    ev = t[above].groupby(event).agg(start="min", end="max")
    long_enough = (ev["end"] - ev["start"]) / pd.Timedelta(minutes=1) >= EVENT_MIN_MIN
    return ev[long_enough].reset_index(drop=True)


def event_volumes(c: pd.DataFrame, nominal_m3: float) -> pd.DataFrame:
    """Pressure drop [mbar] and gas withdrawn [L at 20 degC, 101.325 kPa] per cooking event."""
    p = c.dropna(subset=["pressure"]).sort_values("timestamp")
    t, pressure = pd.DatetimeIndex(p["timestamp"]), p["pressure"].to_numpy()
    before, after = pd.Timedelta(minutes=PRE_MIN), pd.Timedelta(minutes=POST_MIN)
    rows = []
    for ev in cooking_events(c).itertuples():
        pre = pressure[t.searchsorted(ev.start - before, "left"):t.searchsorted(ev.start, "right")]
        post = pressure[t.searchsorted(ev.end, "left"):t.searchsorted(ev.end + after, "right")]
        if not len(pre) or not len(post):
            continue
        high, low = pre.max(), post.min()
        if high - low <= DROP_MIN:
            continue
        to_reference = ((P_ATM_MBAR + 0.5 * (high + low)) / P_ATM_MBAR) * ((273.15 + T_REF_C) / (273.15 + T_DOME_C))
        rows.append({"start": ev.start, "drop_mbar": high - low,
                     "volume_L": storage_constant(nominal_m3) * (high - low) * to_reference})
    return pd.DataFrame(rows, columns=["start", "drop_mbar", "volume_L"])


def nominal_volumes() -> pd.Series:
    """Nominal digester volume [m3] of the compared units, from the survey."""
    survey = pd.read_csv(DATA_REPO / "data" / "survey.csv").set_index("sensor")["digester_m3"]
    return survey[sorted(set(survey.index) - NOT_HOUSEHOLD - FAILED - VALVE_UNITS - PRESSURE_FAULT_UNITS)]


def daily_pressure_volumes() -> pd.DataFrame:
    """Pressure-based gas volume [L] per unit and UTC day, for the usable units with a usable pressure."""
    out = []
    for sen, nominal_m3 in nominal_volumes().items():
        c = corrected(sen)
        ev = event_volumes(c[c["timestamp"] <= PILOT_END], float(nominal_m3))
        daily = ev.groupby(ev["start"].dt.date)["volume_L"].sum()
        out.append(pd.DataFrame({"unit": sen[3:], "day": daily.index, "pressure_L": daily.to_numpy()}))
    return pd.concat(out, ignore_index=True)


def comparison() -> pd.DataFrame:
    """Valid unit-days of the compared units with the thermal and the pressure-based volume [L]."""
    pressure = daily_pressure_volumes()
    thermal = daily_volumes()
    thermal = thermal[thermal["unit"].isin(pressure["unit"].unique())]
    return thermal.merge(pressure, on=["unit", "day"], how="left")


def unit_ratios(days: pd.DataFrame) -> pd.Series:
    """Per unit, the median over its days of thermal / pressure-based daily volume."""
    both = days[(days["volume_L"] > 0) & (days["pressure_L"] > 0)]
    return (both["volume_L"] / both["pressure_L"]).groupby(both["unit"]).median()


def bands(ratios: pd.Series) -> dict[str, pd.Series]:
    """Unit ratios within BAND of their median, below and above. The split does not depend on STORE_FRACTION."""
    rel = ratios / ratios.median()
    return {"within": ratios[(rel >= 1 - BAND) & (rel <= 1 + BAND)],
            "lower": ratios[rel < 1 - BAND], "higher": ratios[rel > 1 + BAND]}


def main():
    days = comparison()
    both = days[(days["volume_L"] > 0) & (days["pressure_L"] > 0)]
    r = unit_ratios(days)
    b = bands(r)
    span = lambda x: f"{len(x)} ({x.min():.2f}-{x.max():.2f})"
    print("[Methods, Table S3] storage constant: "
          + ", ".join(f"{storage_constant(v):.1f} L/mbar for {v} m3" for v in (8, 10, 12)))
    p99 = {u[3:]: corrected(u)["pressure"].quantile(0.99) for u in sorted(PRESSURE_FAULT_UNITS)}
    print("[Table S3] left out: pressure follows a closed valve "
          + ", ".join(sorted(u[3:] for u in VALVE_UNITS)) + "; impaired pressure sensor "
          + ", ".join(f"{u} (99th percentile {v:.1f} mbar)" for u, v in p99.items()))
    print(f"[Methods, Table S3] units compared {r.size}; valid days {len(days):,}, with a thermal volume "
          f"{(days['volume_L'] > 0).sum():,}, with both volumes {len(both):,}")
    print(f"[Methods, Table S3] unit ratio thermal / pressure-based (median of daily ratios): median {r.median():.2f}, "
          f"IQR {r.quantile(.25):.2f}-{r.quantile(.75):.2f}, range {r.min():.2f}-{r.max():.2f}")
    print(f"[Methods, Table S3] unit ratios within {BAND:.0%} of their median: {span(b['within'])}; lower: "
          f"{span(b['lower'])}; higher: {span(b['higher'])}")
    # every ratio is proportional to the pressure at which the store is taken to be full
    print("[Methods, Table S3] median unit ratio for another full-store pressure: "
          + ", ".join(f"{r.median() * p / P_FULL_MBAR:.2f} at {p:.0f} mbar" for p in P_FULL_RANGE_MBAR))
    print(f"[Table S3] summed over the compared unit-days: thermal {both['volume_L'].sum() / 1e3:,.0f} m3, "
          f"pressure-based {both['pressure_L'].sum() / 1e3:,.0f} m3")


if __name__ == "__main__":
    main()
