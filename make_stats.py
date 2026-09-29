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

from make_figures import RAW, NOT_HOUSEHOLD, FAILED, PILOT_END, load_sensor_times

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

    # -- completeness (same definition as Figure 1)
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
    print(f"[Feasibility, Discussion, Fig. 1] 01018 last sensor record {ts[s].max().date()}; "
          f"10-min reporting slots with a packet {slots:.1%}; valid one-minute records {valid:.1%} of expected")

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
    print("[Feasibility, Fig. 1] fleet-wide gaps (< half the units reporting): "
          + "; ".join(f"{a} to {b} (min {reporting.loc[a:b].min()} units)" for a, b in runs
                      if (pd.Timestamp(b) - pd.Timestamp(a)).days >= 2))


if __name__ == "__main__":
    main()
