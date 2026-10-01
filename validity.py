"""Layered data-validity classification of every unit-day.

Each household unit-day passes four checks in order:

1. link      -- were connectivity heartbeats received (10-min slots)?
2. data      -- were one-minute sensor records received?
3. sensor    -- did the unit log more than RESET_MAX flow-sensor resets that day?
4. use       -- did the unit spend at least USE_MIN minutes in the measuring state
                (state 0)? The firmware stays in that state only while gas flows,
                so a healthy unit below the threshold had no gas use that day.

The thresholds were set from this fleet (healthy units never logged more than 10
resets a day) and are heuristics to be tested on other deployments. "Valid" means
the sensor was alive and measuring, not that its readings are accurate.

Used by make_stats.py (the counts quoted in the paper) and make_figures.py
(Figure 1).
"""
from __future__ import annotations
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from make_figures import RAW, NOT_HOUSEHOLD, PILOT_END

RESET_MAX = 20        # flow-sensor resets per day above which a unit-day shows fault signs
USE_MIN = 20          # measuring-state minutes per day at or above which gas was used
CLASSES = ["valid: gas used", "valid: no use", "partial data", "offline: fleet-wide",
           "offline: single unit", "silent: link up, no data", "sensor fault signs"]


def daily_indicators() -> pd.DataFrame:
    """One row per household unit-day from the first sensor record to the pilot end."""
    rows = []
    for u in sorted({Path(d).name for d in glob.glob(str(RAW / "SN_*"))} - NOT_HOUSEHOLD):
        d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(RAW / u / "*.parquet")))],
                      ignore_index=True)
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
        d = d[d["timestamp"] <= PILOT_END]
        for col in ("state", "msg"):
            if col not in d:
                d[col] = np.nan
        d["day"] = d["timestamp"].dt.date
        resets = d["msg"].astype(str).str.contains("reset BOMAD_FLOW").groupby(d["day"]).sum()
        sens, hb = d[d["state"].notna()], d[d["state"].isna()]
        rec = sens["timestamp"].dt.floor("min").groupby(sens["day"]).nunique() / 1440
        s0 = sens[sens["state"] == 0]
        s0_min = s0["timestamp"].dt.floor("min").groupby(s0["day"]).nunique()
        hb_slots = hb["timestamp"].dt.floor("10min").groupby(hb["day"]).nunique() / 144
        days = pd.date_range(sens["timestamp"].min().normalize(), PILOT_END.normalize(), freq="D").date
        frame = pd.DataFrame({"unit": u[3:], "day": days})
        for name, s in (("hb_slots", hb_slots), ("rec", rec), ("s0_min", s0_min), ("resets", resets)):
            frame[name] = frame["day"].map(s).fillna(0)
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def classify(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add a `cls` column (one of CLASSES) and an uptime-view flag `dashboard_online`."""
    df = daily_indicators() if df is None else df.copy()
    df = df[df["day"] > df.groupby("unit")["day"].transform("min")]          # drop the installation day
    offline = (df["hb_slots"] < 0.1) & (df["rec"] < 0.1)
    fleet = offline.groupby(df["day"]).transform("mean") >= 0.5             # half the fleet dark the same day
    cls = np.select(
        [offline & fleet, offline,
         (df["hb_slots"] >= 0.5) & (df["rec"] < 0.05),
         df["resets"] > RESET_MAX,
         df["rec"] < 0.5,
         df["s0_min"] >= USE_MIN],
        ["offline: fleet-wide", "offline: single unit", "silent: link up, no data",
         "sensor fault signs", "partial data", "valid: gas used"],
        default="valid: no use")
    df["cls"] = cls
    df["dashboard_online"] = df["hb_slots"] >= 0.5                         # what an uptime view shows
    return df.reset_index(drop=True)
