from __future__ import annotations
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MultipleLocator

import os

# The data repository (ecotrace-pilot-data-kiambu): ECOTRACE_DATA if set, else a
# sibling checkout next to this repo. fig_coverage reads the raw Parquet (it
# measures telemetry completeness, which the derived CSVs deliberately collapse);
# fig_diurnal reads the derived CSVs, so it uses the canonical corrected flow
# rather than re-deriving it here.
_env = os.environ.get("ECOTRACE_DATA")
if _env:
    DATA_REPO = Path(_env).expanduser().resolve()
    if not DATA_REPO.is_dir():
        raise FileNotFoundError(
            f"ECOTRACE_DATA={_env!r} does not point at a directory "
            f"(resolved to {DATA_REPO}). Run scripts/get_data.sh to fetch the "
            "dataset, or fix/unset ECOTRACE_DATA."
        )
else:
    DATA_REPO = Path(__file__).resolve().parents[1] / "ecotrace-pilot-data-kiambu"
    if not DATA_REPO.is_dir():
        raise FileNotFoundError(
            f"Cannot locate the ecotrace dataset repository at {DATA_REPO}. "
            "Run scripts/get_data.sh to fetch it, or set ECOTRACE_DATA to the "
            "root of an existing checkout."
        )
RAW = DATA_REPO / "data" / "raw_data"
DERIVED = DATA_REPO / "data" / "derived_data"
STYLE = Path(__file__).resolve().parent / "scientific.mplstyle"
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

TZ = "Africa/Nairobi"
NOT_HOUSEHOLD = {"SN_01005", "SN_01010"}   # ILRI research reactors, excluded on scope
# Units failing the inclusion criterion (see fig_coverage docstring). Kept in the
# figure as documented field failures; excluded from all statistics.
FAILED = {"SN_01012", "SN_01018", "SN_01023"}
PILOT_END = pd.Timestamp("2026-07-19 23:59:59", tz="UTC")   # fixed publication cutoff
OKABE_BLUE = "#0072B2"
OKABE_VERM = "#D55E00"

# Single-hue sequential ramp, light -> dark (magnitude). A deployed-but-silent day
# is 0.0 and renders at the light end; only pre-installation is N/A (warm grey), so
# "no data" can never be misread as "low completeness".
UPTIME_CMAP = ["#e3edfa", "#a9c9ee", "#5f9ae0", "#2a78d6", "#1a4f96", "#0e2f5c"]
NA_GREY = "#e0ddd6"


def set_mpl():
    plt.style.use(["default", str(STYLE)])
    plt.rcParams["figure.constrained_layout.use"] = False


def corrected(sen: str) -> pd.DataFrame:
    """Concatenate the canonical derived CSVs for one sensor.

    These already carry the swap-corrected ``flow_corrected`` / ``comp_corrected``
    produced by the data repository's derivation, so nothing is recomputed here.
    """
    frames = [pd.read_csv(f) for f in sorted(glob.glob(str(DERIVED / sen / "*.csv")))]
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df

def load_sensor_times(sen: str) -> pd.DatetimeIndex:
    """Timestamps of SENSOR rows only, truncated at PILOT_END.

    Heartbeat rows carry no measurement (battery/RSSI on a 600 s timer, mem_free on
    a 300 s timer, ~432/day) and are identified by a null ``state``; they are dropped
    so the denominator is the 1440 expected one-minute sensor records per day.
    Some files predate the ``state`` column and are heartbeat-only -- these contain
    no sensor rows at all. Counting them is what made a dead unit look 30-40% complete.
    """
    frames = []
    for f in sorted(glob.glob(str(RAW / sen / "*.parquet"))):
        if "state" not in set(pq.ParquetFile(f).schema_arrow.names):
            continue
        df = pd.read_parquet(f, columns=["timestamp", "state"])
        frames.append(df[df["state"].notna()])
    ts = pd.to_datetime(pd.concat(frames, ignore_index=True)["timestamp"], utc=True).dropna()
    return pd.DatetimeIndex(ts[ts <= PILOT_END].sort_values())

def fig_coverage():
    """Daily telemetry completeness per household unit, over a fixed pilot window.

    Cell = distinct one-minute bins containing a sensor record, / 1440.
    This measures the link: powered, looping, and delivering. It deliberately does
    NOT claim to measure sensor health -- no reachable device state encodes a fault
    (safety checks are compiled out), so the telemetry carries no health signal.
    Days after a unit's installation with no records are 0.0, not missing.
    """
    households = sorted({Path(d).name for d in glob.glob(str(RAW / "SN_*"))} - NOT_HOUSEHOLD)
    recs, first, uptime = {}, {}, {}
    for sen in households:
        ts = load_sensor_times(sen)
        first[sen] = ts[0]
        by_day = (ts.floor("min").to_series().groupby(ts.date).nunique() / 1440.0).clip(upper=1.0)
        recs[sen] = by_day
        span = (PILOT_END.normalize() - ts[0].normalize()).days + 1
        uptime[sen] = by_day.sum() / span

    # All units are plotted and rendered identically; the excluded ones simply sort
    # to the bottom on their own merit. Which units are excluded is stated in the
    # caption, not encoded in the graphics.
    order = sorted(households, key=lambda s: uptime[s], reverse=True)
    keep = [s for s in order if s not in FAILED]
    drop = [s for s in order if s in FAILED]

    start = min(first.values()).normalize().date()
    days = pd.date_range(start, PILOT_END.normalize().date(), freq="D").date
    day_ix = {d: i for i, d in enumerate(days)}
    M = np.full((len(order), len(days)), np.nan)
    for r, sen in enumerate(order):
        M[r, day_ix[first[sen].date()]:] = 0.0     # deployed but silent = 0, not missing
        for d, v in recs[sen].items():
            if d in day_ix:
                M[r, day_ix[d]] = v

    from matplotlib.colors import LinearSegmentedColormap
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    # cmap = LinearSegmentedColormap.from_list("uptime", UPTIME_CMAP)
    # cmap.set_bad(NA_GREY)                          # pre-installation only
    cmap = "cividis_r"
    x0 = mdates.date2num(start)
    im = ax.imshow(M, aspect="auto", cmap=cmap, vmin=0, vmax=1,
                   extent=[x0, x0 + len(days), len(order) - 0.5, -0.5],
                   interpolation="nearest")
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([s.replace("SN_", "") for s in order], fontsize=7)
    ax.tick_params(axis="y", length=0)
    ax.minorticks_off()
    ax.set_ylabel(r"monitoring unit")
    ax.set_xlabel(r"2026")
    cax = make_axes_locatable(ax).append_axes("right", size="3%", pad=0.15)
    fig.colorbar(im, cax=cax, label=r"daily telemetry completeness")
    fig.tight_layout()
    out = OUT / "fig_coverage.png"
    fig.savefig(out, dpi=400)
    plt.close(fig)
    inc = np.array([uptime[s] for s in keep])
    print("wrote", out)
    print(f"  included {len(keep)}/{len(households)} | median uptime {np.median(inc):.3f}"
          f" | IQR {np.percentile(inc,25):.3f}-{np.percentile(inc,75):.3f}"
          f" | range {inc.min():.3f}-{inc.max():.3f}")
    for s in drop:
        print(f"  EXCLUDED {s}: uptime {uptime[s]:.3f}, last record {recs[s].index.max()}")


def fig_diurnal(sen="SN_01015", min_day_records=20):
    df = corrected(sen)
    d = df[df["state"] == 0].dropna(subset=["flow_corrected"]).copy()
    loc = d["timestamp"].dt.tz_convert(TZ)
    d["hour"], d["day"] = loc.dt.hour, loc.dt.date
    daily = (d.groupby(["day", "hour"])["flow_corrected"].mean()
               .unstack("hour").reindex(columns=range(24)).fillna(0.0))
    daily = daily[d.groupby("day").size().reindex(daily.index) >= min_day_records]
    daily = daily[daily.sum(axis=1) > 0]
    dailyN = daily.div(daily.sum(axis=1), axis=0) * 100.0 # each day sums to 100%
    x = np.arange(24)
    mean = dailyN.mean(axis=0).values
    lo, hi = dailyN.quantile(0.25).values, dailyN.quantile(0.75).values
    ndays = len(dailyN)

    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    ax.fill_between(x, lo, hi,
                    color=OKABE_BLUE,
                    alpha=0.16,
                    lw=0,
                    label=r"25--75th percentile across days",
                    zorder=1)
    ax.plot(x, mean,
            color=OKABE_BLUE,
            lw=1.5,
            #marker="o", ms=3.2,
            label=fr"mean of {ndays} days",
            zorder=2)
    for lab, win in [("breakfast", range(5, 10)), ("lunch", range(11, 15)), ("dinner", range(17, 22))]:
        hr = max(win, key=lambda h: mean[h])
        ax.annotate(lab,
                    xy=(hr, mean[hr]),
                    xytext=(0, 7),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8.5,
                    color="0.25")
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 20)
    ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21, 24])
    ax.xaxis.set_minor_locator(MultipleLocator(1))   # minor ticks on every whole hour
    ax.set_xlabel(r"hour of day (Nairobi, Kenya)")
    ax.set_ylabel(r"share of daily use / \%")
    ax.legend(loc="upper right", fontsize=8.5)
    fig.tight_layout()
    out = OUT / "fig_diurnal.png"
    fig.savefig(out)
    plt.close(fig)
    print("wrote", out, "| ndays:", ndays, "| peak hours:",
          [int(h) for h in np.argsort(mean)[-3:]])


if __name__ == "__main__":
    set_mpl()
    fig_coverage()
    fig_diurnal()
