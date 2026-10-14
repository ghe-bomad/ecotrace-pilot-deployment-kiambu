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
# Units failing the inclusion criterion: a unit is usable only if it was still
# returning sensor records in the final week of the pilot (make_stats.py checks
# that this set is exactly what the rule excludes). Kept in the figure as
# documented field failures; excluded from all statistics.
FAILED = {"SN_01012", "SN_01018", "SN_01023"}
PILOT_END = pd.Timestamp("2026-07-19 23:59:59", tz="UTC")   # fixed publication cutoff
# Single-series figures (2 and 3) are grayscale; Figure 1 keeps its categorical
# validity palette.
INK = "0.15"         # medians, lines
EDGE = "0.35"        # box edges, whiskers, caps
FILL = "0.86"        # box fill
BAND = "0.15"        # Figure 2 interquartile band (drawn with alpha)
FLIER = "0.55"       # outlier circles

# Perceptually uniform, colour-blind safe, reversed so low completeness is light
# and high is dark. A deployed-but-silent day is 0.0 and renders at the light end;
# only pre-installation is masked, and it is painted NA_GREY (a warm grey outside
# the ramp) so "no data" can never be misread as "low completeness".
UPTIME_CMAP = "cividis_r"
NA_GREY = "#e0ddd6"


def unit_order(units) -> list[str]:
    """Units by ascending number, the order used in Figures 1 and 3."""
    return sorted(str(u).replace("SN_", "") for u in units)


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

    from mpl_toolkits.axes_grid1 import make_axes_locatable
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    cmap = plt.get_cmap(UPTIME_CMAP).copy()
    cmap.set_bad(NA_GREY)                            # pre-installation only
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
    fig.savefig(OUT / "fig_coverage.png")
    fig.savefig(OUT / "fig_coverage.pdf")
    plt.close(fig)
    inc = np.array([uptime[s] for s in keep])
    print(f"included {len(keep)}/{len(households)} | median uptime {np.median(inc):.3f}"
          f" | IQR {np.percentile(inc,25):.3f}-{np.percentile(inc,75):.3f}"
          f" | range {inc.min():.3f}-{inc.max():.3f}")
    for s in drop:
        print(f"  EXCLUDED {s}: uptime {uptime[s]:.3f}, last record {recs[s].index.max()}")


def fig_validity():
    """Figure 1: validity class of every household unit-day (four checks, see validity.py).

    Rows are ordered by unit number, as in Figure 3; the three units excluded from
    the statistics are marked with an asterisk and grey labels. Colours: teal = valid (dark: gas used, light: no use); warm neutrals =
    delivery problems; amber = silent (link up, no data); violet = sensor fault signs.
    The coloured classes were checked for lightness, chroma, colour-vision-deficiency
    and normal-vision separation, and 3:1 contrast on white.
    """
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    from validity import classify
    colours = {"valid: gas used": "#00897B", "valid: no use": "#9ED6CE", "partial data": "#D6C59B",
               "offline: fleet-wide": "#A7A29A", "offline: single unit": "#5C5852",
               "silent: link up, no data": "#B8650A", "sensor fault signs": "#6A3D9A"}
    not_installed = "#F5F3EF"
    df = classify()
    df["day"] = pd.to_datetime(df["day"])
    failed = {u[3:] for u in FAILED}
    units = unit_order(df["unit"].unique())
    days = pd.date_range(df["day"].min(), df["day"].max(), freq="D")
    idx = {c: i for i, c in enumerate(colours)}
    M = np.full((len(units), len(days)), np.nan)
    col = {d: i for i, d in enumerate(days)}
    for r in df.itertuples():
        M[units.index(r.unit), col[r.day]] = idx[r.cls]
    cmap = ListedColormap(list(colours.values())); cmap.set_bad(not_installed)
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    x0 = mdates.date2num(days[0])
    ax.imshow(np.ma.masked_invalid(M), aspect="auto", cmap=cmap, vmin=-0.5, vmax=len(colours) - 0.5,
              extent=[x0, x0 + len(days), len(units) - 0.5, -0.5], interpolation="nearest")
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_yticks(range(len(units)))
    ax.set_yticklabels([f"{u}*" if u in failed else u for u in units], fontsize=7)
    for lab, u in zip(ax.get_yticklabels(), units):
        if u in failed:
            lab.set_color(FLIER)
    ax.tick_params(axis="y", length=0); ax.minorticks_off()
    ax.set_ylabel(r"monitoring unit"); ax.set_xlabel(r"2026")
    handles = [Patch(facecolor=c, label=l) for l, c in colours.items()]
    handles.append(Patch(facecolor=not_installed, edgecolor="#bdb8ad", linewidth=0.5, label="not yet installed"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=4, fontsize=7.5,
              frameon=False, handlelength=1.2, columnspacing=1.0)
    fig.set_layout_engine("none")
    fig.subplots_adjust(left=0.1, right=0.98, top=0.98, bottom=0.27)
    fig.savefig(OUT / "Figure_1.png", bbox_inches=None)
    fig.savefig(OUT / "Figure_1.pdf", bbox_inches=None)
    plt.close(fig)


# Rows below the dataset's no-flow gate are idle: a unit at its zero still reads
# about 0.02 L/min on the King's-law inverse, which is not gas use.
NO_FLOW_MAX = 0.5   # L/min


def daily_volume(c: pd.DataFrame) -> pd.Series:
    """Litres of gas per UTC day from one unit's state-0 rows.

    The dataset's volume definition (data repository,
    data/derived_data/README.md, "Computing gas volumes"): rows are one minute
    apart while the unit measures, so each row's ``flow_zero_cal`` [L/min] is a
    litre count, rows below NO_FLOW_MAX are idle and not counted, and
    ``gap_fill_L`` adds the gas that flowed while the unit slept during use.
    Days are UTC dates, the keys validity.py classifies, so volumes join the
    valid days directly.
    """
    c = c[c["timestamp"] <= PILOT_END]
    measured = c["flow_zero_cal"].where(c["flow_zero_cal"] >= NO_FLOW_MAX, 0.0)
    return (measured + c["gap_fill_L"]).groupby(c["timestamp"].dt.date).sum()


def daily_volumes() -> pd.DataFrame:
    """Daily gas volume [L] per usable household on valid days (Figure 4).

    Uses ``flow_zero_cal``, the flow with each unit's zero-flow offset removed,
    and ``gap_fill_L``, the unmeasured gas next to rows in use (data repository,
    docs/field_correction.md sections 7 and 8). A valid day without measuring
    rows has zero volume. The interiors of gaps longer than one sleep cycle are
    not filled, so volumes are a lower bound there.
    """
    from validity import classify
    valid = classify()
    valid = valid[~valid["unit"].isin([u[3:] for u in FAILED]) & valid["cls"].str.startswith("valid")]
    out = []
    for unit in sorted(valid["unit"].unique()):
        v = daily_volume(corrected(f"SN_{unit}"))
        days = valid.loc[valid["unit"] == unit, "day"]
        out.append(pd.DataFrame({"unit": unit, "day": days.to_numpy(),
                                 "volume_L": days.map(v).fillna(0.0).to_numpy()}))
    return pd.concat(out, ignore_index=True)


def _boxes(ax, data, labels):
    ax.boxplot(data, widths=0.55, showfliers=True, patch_artist=True,
               boxprops=dict(facecolor=FILL, edgecolor=EDGE, linewidth=0.8),
               medianprops=dict(color=INK, linewidth=1.5),
               whiskerprops=dict(color=EDGE, linewidth=0.8), capprops=dict(color=EDGE, linewidth=0.8),
               flierprops=dict(marker="o", markersize=2.2, markerfacecolor="none", markeredgecolor=FLIER,
                               markeredgewidth=0.5))
    ax.set_xticks(range(1, len(labels) + 1)); ax.set_xticklabels(labels, rotation=90, fontsize=7.5)
    ax.tick_params(axis="x", which="both", length=0, top=False); ax.tick_params(axis="y", right=False)
    ax.minorticks_off()
    ax.set_ylim(bottom=0)


def fig_use():
    """Figure 3: daily gas use per usable household on valid days.

    (a) Duration: minutes per day in sustained measuring-state runs with corrected
    flow at or above the 2 L/min deadband (validity.py), as hours; the flow is an
    on/off test here. (b) Volume: the dataset's gap-filled, zero-calibrated volume
    (``daily_volumes``). Units in ascending number, as in Figure 1.
    """
    from validity import classify
    df = classify()
    df = df[~df["unit"].isin([u[3:] for u in FAILED]) & df["cls"].str.startswith("valid")]
    vol = daily_volumes()
    order = unit_order(df["unit"].unique())
    duration = [df.loc[df["unit"] == u, "use_min"].to_numpy() / 60 for u in order]
    volume = [vol.loc[vol["unit"] == u, "volume_L"].to_numpy() / 1000 for u in order]
    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.6, 5.8), sharex=True)
    _boxes(ax_a, duration, order)
    _boxes(ax_b, volume, order)
    ax_a.set_ylabel(r"gas-use duration / h day$^{-1}$")
    ax_b.set_ylabel(r"gas volume / m$^3$ day$^{-1}$")
    ax_b.set_xlabel(r"monitoring unit")
    for ax, lab in ((ax_a, "(a)"), (ax_b, "(b)")):
        ax.text(0.0, 1.02, lab, transform=ax.transAxes, ha="left", va="bottom", fontsize=9)
    fig.align_ylabels((ax_a, ax_b))
    fig.savefig(OUT / "Figure_3.png")
    fig.savefig(OUT / "Figure_3.pdf")
    plt.close(fig)


def daily_profiles(sen="SN_01015", min_day_records=20) -> pd.DataFrame:
    """One row per day, 24 hour-of-day columns, each day normalised to sum to 100%."""
    df = corrected(sen)
    # The derived CSVs already contain state-0 rows only (derive.py filters at
    # ingest); the filter is kept as a guard against an older derivation.
    d = df[df["state"] == 0].dropna(subset=["flow_corrected"]).copy()
    loc = d["timestamp"].dt.tz_convert(TZ)
    d["hour"], d["day"] = loc.dt.hour, loc.dt.date
    # hourly SUM of flow, so each hour's share is its share of the day's gas use;
    # a mean would be diluted by the idle-wake samples logged when no gas flows
    daily = (d.groupby(["day", "hour"])["flow_corrected"].sum()
               .unstack("hour").reindex(columns=range(24)).fillna(0.0))
    daily = daily[d.groupby("day").size().reindex(daily.index) >= min_day_records]
    daily = daily[daily.sum(axis=1) > 0]
    return daily.div(daily.sum(axis=1), axis=0) * 100.0 # each day sums to 100%


def fig_diurnal(sen="SN_01015", min_day_records=20):
    dailyN = daily_profiles(sen, min_day_records)
    x = np.arange(24)
    mean = dailyN.mean(axis=0).values
    lo, hi = dailyN.quantile(0.25).values, dailyN.quantile(0.75).values
    ndays = len(dailyN)

    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    ax.fill_between(x, lo, hi,
                    color=BAND,
                    alpha=0.15,
                    lw=0,
                    label=r"25--75th percentile across days",
                    zorder=1)
    ax.plot(x, mean,
            color=INK,
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
    ax.set_ylim(0, max(hi.max(), mean.max()) * 1.12)
    ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21, 24])
    ax.xaxis.set_minor_locator(MultipleLocator(1))   # minor ticks on every whole hour
    ax.set_xlabel(r"hour of day (Nairobi, Kenya)")
    ax.set_ylabel(r"share of daily use / \%")
    ax.legend(loc="upper right", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "Figure_2.png")
    fig.savefig(OUT / "Figure_2.pdf")
    plt.close(fig)
    print("\nndays:", ndays, "| peak hours:",
          [int(h) for h in np.argsort(mean)[-3:]])


if __name__ == "__main__":
    set_mpl()
    fig_validity()
    fig_coverage()
    fig_diurnal()
    fig_use()
