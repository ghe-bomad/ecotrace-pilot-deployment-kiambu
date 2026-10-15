"""Reproduce every number the paper quotes that is not read off a figure.

Prints one line per statistic, labelled with where it appears in the paper.
Reads the same raw Parquet as make_figures.py and reuses its loaders and
constants, so the unit sets, pilot window and completeness definition cannot
drift between the figures and the text.

    python3 make_stats.py
"""
from __future__ import annotations
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from make_figures import (RAW, NOT_HOUSEHOLD, FAILED, PILOT_END, NO_FLOW_MAX, H2S_RANGE_PPM,
                          load_sensor_times, corrected, daily_volumes, composition_table)
from validity import CLASSES, classify

# Inclusion rule: a unit is "usable" if it was still returning sensor records in
# the final week of the pilot. FAILED in make_figures.py must equal the set this
# rule excludes; main() asserts it.
FINAL_WEEK_START = PILOT_END.normalize() - pd.Timedelta(days=6)
MONTHS_REDUCED = ["2026-05", "2026-06", "2026-07"]   # 01013's reduced-completeness months


def households() -> list[str]:
    return sorted({Path(d).name for d in glob.glob(str(RAW / "SN_*"))} - NOT_HOUSEHOLD)


def load_all(sen: str, columns: list[str]) -> pd.DataFrame:
    """Every row (sensor and heartbeat) with the requested columns that exist."""
    frames = []
    for f in sorted(glob.glob(str(RAW / sen / "*.parquet"))):
        have = set(pq.ParquetFile(f).schema_arrow.names)
        cols = [c for c in columns if c in have]
        frames.append(pd.read_parquet(f, columns=["timestamp", *[c for c in cols if c != "timestamp"]]))
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df[df["timestamp"] <= PILOT_END]


def daily_completeness(ts: pd.DatetimeIndex) -> pd.Series:
    """Share of the 1440 expected one-minute sensor records received, per day."""
    return (ts.floor("min").to_series().groupby(ts.date).nunique() / 1440.0).clip(upper=1.0)


def main():
    units = households()
    ts = {s: load_sensor_times(s) for s in units}

    # -- inclusion rule
    excluded = {s for s in units if ts[s].max() < FINAL_WEEK_START}
    assert excluded == FAILED, f"inclusion rule excludes {sorted(excluded)}, FAILED is {sorted(FAILED)}"
    kept = [s for s in units if s not in excluded]
    print(f"[Methods] units usable (measuring in final week from {FINAL_WEEK_START.date()}): "
          f"{len(kept)}/{len(units)}; excluded {sorted(s[3:] for s in excluded)}")

    # -- completeness (same record definition as Figure 2)
    comp, active, med_active = {}, {}, {}
    for s in kept:
        by_day = daily_completeness(ts[s])
        span = (PILOT_END.normalize() - ts[s][0].normalize()).days + 1
        comp[s] = by_day.sum() / span
        active[s] = int((by_day > 0).sum())
        med_active[s] = by_day[by_day > 0].median()
    c = np.array(list(comp.values()))
    print(f"[Abstract, Table 1] median telemetry completeness {np.median(c):.1%} "
          f"(IQR {np.percentile(c, 25):.1%}-{np.percentile(c, 75):.1%})")
    print(f"[Table 1] median active days/unit {np.median(list(active.values())):.0f}; "
          f"median completeness on days with any data {np.median(list(med_active.values())):.1%}")

    # -- deployment totals over the analysed units
    # device-days = days on which a unit returned any sensor record
    days = sum(active.values())
    recs = sum(len(ts[s]) for s in kept)
    print(f"[Deployment] {days:,} device-days with data ({days * 24:,} device-hours), "
          f"{recs / 1e6:.1f} million sensor records across {len(kept)} units")

    # -- duty cycle: which device states the received sensor records are in, and
    #    how many expected minutes carry a normal-measuring (state 0) record
    counts, measured, expected = pd.Series(dtype=float), 0, 0
    for u in kept:
        st = load_all(u, ["state"]).dropna(subset=["state"])
        counts = counts.add(st["state"].value_counts(), fill_value=0)
        measured += st.loc[st["state"] == 0, "timestamp"].dt.floor("min").nunique()
        expected += ((PILOT_END.normalize() - ts[u][0].normalize()).days + 1) * 1440
    share = counts / counts.sum()
    print(f"[Methods] received sensor records by state: normal {share.get(0, 0):.0%}, "
          f"warm-up {share.get(1, 0):.0%}, sleep {share.get(5, 0):.0%}, low voltage {share.get(6, 0):.2%}; "
          f"minutes with a normal-measuring record {measured / expected:.0%} of expected")

    # -- 01013: included, but reduced completeness late in the pilot
    by_day = daily_completeness(ts["SN_01013"])
    monthly = by_day.groupby(pd.PeriodIndex(pd.to_datetime(by_day.index), freq="M")).mean()
    late = monthly[[pd.Period(m, "M") for m in MONTHS_REDUCED]]
    print(f"[Feasibility] 01013 monthly mean completeness "
          + ", ".join(f"{p}: {v:.0%}" for p, v in late.items()))

    # -- 01018: silent failure
    s = "SN_01018"
    hb = load_all(s, ["state"])
    hb = hb[hb["state"].isna()] if "state" in hb else hb
    first = ts[s][0]
    span_days = (PILOT_END.normalize() - first.normalize()).days + 1
    # packets are sent every 10 minutes, so a reporting slot is a 10-min bin
    slots = hb["timestamp"].dt.floor("10min").nunique() / ((PILOT_END - first) / pd.Timedelta("10min"))
    valid = ts[s].floor("min").nunique() / (span_days * 1440)
    print(f"[Feasibility, Discussion, Fig. 2] 01018 last sensor record {ts[s].max().date()}; "
          f"10-min reporting slots with a packet {slots:.1%}; valid one-minute records {valid:.1%} of expected")

    # -- the two units that stopped: battery voltage at their last heartbeat
    for u in ("SN_01012", "SN_01023"):
        b = load_all(u, ["battery_volt"]).dropna(subset=["battery_volt"]).sort_values("timestamp")
        print(f"[Feasibility] {u[3:]} stopped {ts[u].max().date()}; battery at last heartbeat "
              f"{b['battery_volt'].iloc[-1]:.2f} V ({b['timestamp'].iloc[-1]:%Y-%m-%d %H:%M} UTC)")

    # -- reference gas composition (Figure 5): Draeger X-am 8000 spot readings on
    #    the household digesters, treated as ground truth (see composition_table)
    comp = composition_table()
    raw_h2s = comp["H2S_raw"].dropna()
    filt = comp["H2S_filtered"].dropna()
    both = comp.dropna(subset=["H2S_raw", "H2S_filtered"])
    print(f"[Results, Fig. 5] {len(comp)} household digesters: CH4 {comp.CH4.min():.0f}-{comp.CH4.max():.0f} vol-% "
          f"(median {comp.CH4.median():.0f}), CO2 {comp.CO2.min():.0f}-{comp.CO2.max():.0f} vol-% "
          f"(median {comp.CO2.median():.1f}), O2 at most {comp.O2.max():.1f} vol-%")
    print(f"[Results, Fig. 5] H2S in raw gas on {len(raw_h2s)} digesters: {int((raw_h2s >= H2S_RANGE_PPM).sum())} "
          f"at or above the {H2S_RANGE_PPM} ppm range limit, the others {raw_h2s[raw_h2s < H2S_RANGE_PPM].min():.1f}-"
          f"{raw_h2s[raw_h2s < H2S_RANGE_PPM].max():.1f} ppm")
    print(f"[Results, Fig. 5] H2S after the filter on {len(filt)} digesters: {filt.min():.0f}-{filt.max():.1f} ppm "
          f"(median {filt.median():.1f}); measured before and after on {len(both)}, lower after on "
          f"{int((both.H2S_filtered < both.H2S_raw).sum())}")

    # -- data validity (Figure 2): four checks per unit-day, see validity.py
    v = classify()
    counts = v["cls"].value_counts().reindex(CLASSES, fill_value=0)
    print("[Feasibility, Fig. 2] unit-days by validity class (20 units): "
          + ", ".join(f"{c} {n}" for c, n in counts.items()))
    on = v[v["dashboard_online"]]
    bad = on["cls"].isin(["silent: link up, no data", "sensor fault signs"])
    print(f"[Feasibility, Discussion] unit-days an uptime view shows online {len(on):,}; without valid "
          f"measurement {bad.sum()} ({bad.mean():.1%}), units {sorted(on.loc[bad, 'unit'].unique())}")
    f18 = v[v["unit"] == "01018"]
    print(f"[Feasibility] 01018 first fault-sign day {f18.loc[f18.cls == 'sensor fault signs', 'day'].min()}; "
          f"first silent day {f18.loc[f18.cls.str.startswith('silent'), 'day'].min()}; "
          f"silent days {int(f18.cls.str.startswith('silent').sum())}; resets/day on fault days "
          f"{int(f18.loc[f18.cls == 'sensor fault signs', 'resets'].min())}-{int(f18['resets'].max())}")
    others = v[(v["unit"] != "01018") & (v["cls"] == "sensor fault signs")]
    print(f"[Feasibility] fault-sign days on other units: "
          + "; ".join(f"{r.unit} {r.day} ({int(r.resets)} resets)" for r in others.itertuples()))
    print(f"[Feasibility] of these: silent {int((on.cls == 'silent: link up, no data').sum())}, "
          f"fault signs {int((on.cls == 'sensor fault signs').sum())}")
    gaps = [(pd.Timestamp("2026-04-28").date(), pd.Timestamp("2026-05-08").date()),
            (pd.Timestamp("2026-06-24").date(), pd.Timestamp("2026-07-07").date())]
    fw = v[v["cls"] == "offline: fleet-wide"]
    in_gap = fw["day"].apply(lambda d: any(a <= d <= b for a, b in gaps))
    su = v[v["cls"] == "offline: single unit"]
    print(f"[Feasibility] fleet-wide offline unit-days {len(fw)}, of which in the two SIM gaps {int(in_gap.sum())}; "
          f"single-unit offline {len(su)}, of which 01012/01023 {int(su.unit.isin(['01012', '01023']).sum())}")
    usable = v[v["unit"].isin([s[3:] for s in kept])]
    print(f"[Feasibility] usable units: max resets/day excluding those days "
          f"{int(usable.loc[usable.cls != 'sensor fault signs', 'resets'].max())}; classes "
          + ", ".join(f"{c} {n}" for c, n in usable["cls"].value_counts().reindex(CLASSES, fill_value=0).items() if n))

    nu = usable[usable["cls"] == "valid: no use"]
    print(f"[Feasibility] usable units: no-use days {len(nu)}, top units {nu.unit.value_counts().head(3).to_dict()}")
    # -- cooking duration (Figure 4 bottom): sustained, flowing minutes per valid day, per usable unit
    vd = usable[usable["cls"].str.startswith("valid")]
    med_h = vd.groupby("unit")["use_min"].median() / 60
    print(f"[Feasibility, Fig. 4 bottom] median daily cooking duration per unit {med_h.min():.1f}-{med_h.max():.1f} h "
          f"(median across units {med_h.median():.1f} h)")
    # -- gas volume (Figure 4 top): litres per valid day from the zero-calibrated flow
    vol = daily_volumes()
    med_v = vol.groupby("unit")["volume_L"].median() / 1000
    print(f"[Feasibility, Fig. 4 top] median daily gas volume per unit {med_v.min():.2f}-{med_v.max():.2f} m3 "
          f"(median across units {med_v.median():.2f} m3, {len(vol)} valid unit-days)")
    measured = filled = 0.0
    for u in kept:
        c = corrected(u)
        c = c[c["timestamp"] <= PILOT_END]
        measured += c.loc[c["flow_zero_cal"] >= NO_FLOW_MAX, "flow_zero_cal"].sum()
        filled += c["gap_fill_L"].sum()
    print(f"[Feasibility, Fig. 4 top] gas filled into unmeasured time next to use (dataset gap_fill_L): "
          f"{filled / (measured + filled):.1%} of the total")
    sus_min, flow_min, exp_min = 0, 0, 0
    for u in kept:
        c = corrected(u)
        c = c[c["timestamp"] <= PILOT_END].assign(t=c["timestamp"].dt.floor("min")).drop_duplicates("t").sort_values("t")
        run = c.groupby((c["t"].diff() != pd.Timedelta("1min")).cumsum())["t"].transform("size")
        sus_min += int((run >= 3).sum()); flow_min += int(((run >= 3) & (c["flow_corrected"] >= 2)).sum())
        exp_min += ((PILOT_END.normalize() - ts[u][0].normalize()).days + 1) * 1440
    print(f"[Methods] sustained measuring minutes {sus_min / exp_min:.0%} of expected, with flow >= 2 L/min "
          f"{flow_min / exp_min:.0%}; sustained minutes without such flow {1 - flow_min / sus_min:.0%}")

    # -- connectivity: RSSI over the analysed units (heartbeat rows carry it)
    rssi = pd.concat([load_all(u, ["rssi_dbm"])["rssi_dbm"].dropna() for u in kept])
    print(f"[Table 1] RSSI median {rssi.median():.0f} dBm; 25th percentile {rssi.quantile(0.25):.0f} dBm "
          f"(n = {len(rssi):,} readings)")

    # -- power: low-battery shutdowns logged in the msg column
    shut = {}
    for u in kept:
        m = load_all(u, ["msg"])
        if "msg" in m:
            shut[u] = int(m["msg"].astype(str).str.contains("Shutdown reason: low battery").sum())
    hit = {k[3:]: v for k, v in shut.items() if v}
    print(f"[Table 1] low-battery shutdowns {sum(shut.values())} on {len(hit)} of {len(kept)} units {hit}")

    # -- fleet-wide gaps: days on which fewer than half the analysed units reported
    reporting = pd.Series(0, index=pd.date_range(min(ts[u][0] for u in kept).normalize().date(),
                                                 PILOT_END.normalize().date(), freq="D").date)
    for u in kept:
        d = daily_completeness(ts[u])
        reporting.loc[d[d > 0].index.intersection(reporting.index)] += 1
    low = reporting[reporting < len(kept) / 2]
    runs, start, prev = [], None, None
    for day in low.index:
        if prev is None or (pd.Timestamp(day) - pd.Timestamp(prev)).days > 1:
            if start is not None:
                runs.append((start, prev))
            start = day
        prev = day
    if start is not None:
        runs.append((start, prev))
    print("[Feasibility, Fig. 2] fleet-wide gaps (< half the units reporting): "
          + "; ".join(f"{a} to {b} (min {reporting.loc[a:b].min()} units)" for a, b in runs
                      if (pd.Timestamp(b) - pd.Timestamp(a)).days >= 2))


if __name__ == "__main__":
    main()
