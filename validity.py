"""Layered data-validity classification of every unit-day.

Each household unit-day passes four checks in order:

1. link      -- were connectivity heartbeats received (10-min slots)?
2. data      -- were one-minute sensor records received?
3. sensor    -- did the unit log more than RESET_MAX flow-sensor resets that day?
4. use       -- were there at least USE_MIN minutes in sustained measuring-state
                runs (USE_RUN or more consecutive minutes in state 0) with corrected
                flow at or above FLOW_MIN, the firmware's 2 L/min deadband? The unit
                enters state 0 briefly on every wake, so a single one-minute sample can
                come from an idle cycle (whether it is logged depends on how the 5-min
                duty cycle falls on the 1-min logging clock). It stays awake while its
                own flow value is above threshold, but that value is corrupted by the
                thermistor channel swap, so a sustained run alone does not prove gas
                use; the corrected flow is used only as an on/off test, not for volumes.

The checks run in this order: offline (heartbeats and records both under 10 % of
expected; fleet-wide when at least half the units are offline that day), silent
(heartbeats in at least half the 10-min slots, records under 5 %), sensor fault
signs (more than RESET_MAX resets), partial data (records under half the day),
then use. The thresholds were set from this fleet (usable units logged at most 11
resets a day, apart from one 47-reset day early in unit 01020's deployment) and
are heuristics to be tested on other deployments. "Valid" means
the sensor was alive and measuring, not that its readings are accurate.

Used by make_stats.py (the counts quoted in the paper) and make_figures.py
(Figure 1).
"""
from __future__ import annotations
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from make_figures import RAW, NOT_HOUSEHOLD, PILOT_END, corrected

RESET_MAX = 20        # flow-sensor resets per day above which a unit-day shows fault signs
USE_RUN = 3           # consecutive measuring-state minutes that make a sustained run (the unit sleeps 30 s after flow stops)
FLOW_MIN = 2.0        # L/min, the firmware deadband; corrected flow at or above it counts as gas flowing
USE_MIN = 3           # minutes per day of sustained, flowing measurement that mark gas use
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
        c = corrected(u)                                                      # state-0 rows with corrected flow
        c = c[c["timestamp"] <= PILOT_END].assign(t=c["timestamp"].dt.floor("min")).drop_duplicates("t").sort_values("t")
        run = c.groupby((c["t"].diff() != pd.Timedelta("1min")).cumsum())["t"].transform("size")
        flowing = c[(run >= USE_RUN) & (c["flow_corrected"] >= FLOW_MIN)]
        use_min = flowing.groupby(flowing["t"].dt.date).size()                # sustained, flowing minutes
        hb_slots = hb["timestamp"].dt.floor("10min").groupby(hb["day"]).nunique() / 144
        days = pd.date_range(sens["timestamp"].min().normalize(), PILOT_END.normalize(), freq="D").date
        frame = pd.DataFrame({"unit": u[3:], "day": days})
        for name, s in (("hb_slots", hb_slots), ("rec", rec), ("s0_min", s0_min), ("use_min", use_min),
                        ("resets", resets)):
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
         df["use_min"] >= USE_MIN],
        ["offline: fleet-wide", "offline: single unit", "silent: link up, no data",
         "sensor fault signs", "partial data", "valid: gas used"],
        default="valid: no use")
    df["cls"] = cls
    df["dashboard_online"] = df["hb_slots"] >= 0.5                         # what an uptime view shows
    return df.reset_index(drop=True)
