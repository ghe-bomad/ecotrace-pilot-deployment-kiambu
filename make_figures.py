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
# sibling checkout next to this repo. fig_validity reads the raw Parquet (link and
# record checks need every row); fig_diurnal and fig_use read the derived CSVs, so
# they use the canonical corrected flow rather than re-deriving it here. Figure 1,
# the map of installation sites, is produced manually (see figures/README.md).
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
# Single-series figures (3 and 4) are grayscale; Figure 2 keeps its categorical
# validity palette.
INK = "0.15"         # medians, lines
EDGE = "0.35"        # box edges, whiskers, caps
FILL = "0.86"        # box fill
BAND = "0.15"        # Figure 3 interquartile band (drawn with alpha)
FLIER = "0.55"       # outlier circles

# Dräger X-am 8000 upper H2S range limit: readings logged as "max" were at or above it.
H2S_RANGE_PPM = 100
# Figure 5: one colour per series (Okabe-Ito, checked for colour-vision deficiency),
# all circles with a black outline.
COMPOSITION_COLOURS = {"CH4": "#E69F00", "CO2": "#56B4E9",
                       "H2S_raw": "#D55E00", "H2S_filtered": "#009E73"}


def composition_table(raw: dict | None = None) -> pd.DataFrame:
    """Reference gas composition per household unit, from the Dräger spot measurements.

    ``raw`` is the dataset's ``data/biogas_composition.json`` (read when None):
    ``{"01001": [measurement, ...], ...}``. Only household units are kept. The
    main composition (CH4, CO2, O2) comes from the raw-gas reading, or from the
    only reading where a unit was measured after its H2S filter alone. H2S is
    kept apart before (``H2S_raw``) and after (``H2S_filtered``) the filter.
    Readings logged as "max" are set to the analyser's range limit and flagged
    in ``*_sat``. CO (read near zero) and NH3 are not reported.
    """
    import json
    if raw is None:
        raw = json.load(open(DATA_REPO / "data" / "biogas_composition.json"))

    def num(v, limit=None):
        if v == "max":
            return float(limit), True
        try:
            return float(v), False
        except (TypeError, ValueError):
            return float("nan"), False

    rows = []
    households = {f"SN_{k}" for k in raw if k.isdigit()} - NOT_HOUSEHOLD
    for unit in unit_order(households):
        ms = raw[unit]
        before = [m for m in ms if str(m.get("after_H2S_removal")) == "False"]
        after = [m for m in ms if str(m.get("after_H2S_removal")) == "True"]
        main = (before or after)[0]
        h2s_raw, h2s_raw_sat = num(before[0]["H2S_ppm"], H2S_RANGE_PPM) if before else (float("nan"), False)
        h2s_f, h2s_f_sat = num(after[0]["H2S_ppm"], H2S_RANGE_PPM) if after else (float("nan"), False)
        rows.append({"unit": unit, "CH4": num(main["CH4_vol_perc"])[0], "CO2": num(main["CO2_vol_perc"])[0],
                     "O2": num(main.get("O2_vol_perc"))[0],
                     "H2S_raw": h2s_raw, "H2S_raw_sat": h2s_raw_sat,
                     "H2S_filtered": h2s_f, "H2S_filtered_sat": h2s_f_sat})
    return pd.DataFrame(rows)


def unit_order(units) -> list[str]:
    """Units by ascending number, the order used in Figures 2 and 4."""
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

def fig_validity():
    """Figure 2: validity class of every household unit-day (four checks, see validity.py).

    Rows are ordered by unit number, as in Figure 4; the three units excluded from
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
    fig.savefig(OUT / "Figure_2.png", bbox_inches=None)
    fig.savefig(OUT / "Figure_2.pdf", bbox_inches=None)
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
    # one x tick per unit, on the bottom and top edge of both panels; no minor
    # ticks on the categorical axis
    ax.tick_params(axis="x", which="major", length=3.5, width=0.6, bottom=True, top=True,
                   labeltop=False)
    ax.tick_params(axis="y", right=False)
    ax.minorticks_off()
    ax.set_ylim(bottom=0)


def fig_use():
    """Figure 4: daily gas use per usable household on valid days.

    Top: volume, the dataset's gap-filled, zero-calibrated volume
    (``daily_volumes``). Bottom: cooking duration, the minutes per day in
    sustained measuring-state runs with corrected flow at or above the 2 L/min
    deadband (validity.py), as hours; the flow is an on/off test here. The two
    panels share the unit axis; units in ascending number, as in Figure 2.
    """
    from validity import classify
    df = classify()
    df = df[~df["unit"].isin([u[3:] for u in FAILED]) & df["cls"].str.startswith("valid")]
    vol = daily_volumes()
    order = unit_order(df["unit"].unique())
    volume = [vol.loc[vol["unit"] == u, "volume_L"].to_numpy() / 1000 for u in order]
    duration = [df.loc[df["unit"] == u, "use_min"].to_numpy() / 60 for u in order]
    fig, (ax_v, ax_d) = plt.subplots(2, 1, figsize=(6.6, 5.4), sharex=True,
                                     gridspec_kw={"hspace": 0.06})
    _boxes(ax_v, volume, order)
    _boxes(ax_d, duration, order)
    ax_v.set_ylabel(r"gas volume / m$^3$ day$^{-1}$")
    ax_d.set_ylabel(r"cooking duration / h day$^{-1}$")
    ax_d.set_xlabel(r"monitoring unit")
    fig.align_ylabels((ax_v, ax_d))
    fig.savefig(OUT / "Figure_4.png")
    fig.savefig(OUT / "Figure_4.pdf")
    plt.close(fig)


def fig_composition(t: pd.DataFrame | None = None):
    """Figure 5: reference biogas composition per household digester (Dräger X-am 8000).

    Top: CH4 and CO2 in vol-%. Bottom: H2S in ppm before and after the
    household's H2S filter, on one vertical per unit, with an arrow from the
    raw-gas to the after-filter reading where both were measured (left out
    where the two markers overlap); the dashed line is the analyser's upper
    range limit, and readings there were at or above it. One legend in a
    single row below the unit axis. ``t`` is ``composition_table()`` (read
    when None). Returns the (closed) figure.
    """
    from matplotlib.lines import Line2D
    t = composition_table() if t is None else t
    x = np.arange(len(t))
    series = {"CH4": r"CH$_4$", "CO2": r"CO$_2$",
              "H2S_raw": r"H$_2$S, raw gas", "H2S_filtered": r"H$_2$S, after filter"}
    fig, (ax_v, ax_p) = plt.subplots(2, 1, figsize=(6.6, 6.2), sharex=True,
                                     gridspec_kw={"hspace": 0.06})
    ax_p.axhline(H2S_RANGE_PPM, color="0.45", lw=0.7, ls="--", zorder=1)
    ax_p.text(len(t) * 0.62, H2S_RANGE_PPM - 3, r"H$_2$S range limit", color="0.35",
              fontsize=9, ha="center", va="top")
    for col, label in series.items():
        ax = ax_v if col in ("CH4", "CO2") else ax_p
        ax.plot(x, t[col], "o", ms=5.5, mfc=COMPOSITION_COLOURS[col], mec="black",
                mew=0.6, ls="none", zorder=3, clip_on=False, gid=col)
    ax_v.set_ylim(30, 62)
    ax_p.set_ylim(-5, 110)
    # effect of the H2S filter: raw-gas reading -> after-filter reading
    pts_per_ppm = ax_p.get_window_extent().height / np.diff(ax_p.get_ylim())[0] * 72 / fig.dpi
    for xi, raw, filt in zip(x, t["H2S_raw"], t["H2S_filtered"]):
        if np.isnan(raw) or np.isnan(filt) or abs(raw - filt) * pts_per_ppm < 8:
            continue
        ax_p.annotate("", xy=(float(xi), float(filt)), xytext=(float(xi), float(raw)), zorder=2,
                      arrowprops=dict(arrowstyle="-|>", color="0.2", lw=0.8, mutation_scale=8,
                                      shrinkA=3.8, shrinkB=3.8))
    ax_v.set_ylabel(r"volumetric concentration / vol-\%")
    ax_p.set_ylabel(r"volumetric concentration / ppm")
    ax_p.set_xlabel(r"monitoring unit")
    for ax in (ax_v, ax_p):
        ax.set_xticks(x)
        ax.set_xlim(-0.6, len(t) - 0.4)
        ax.tick_params(axis="x", which="minor", bottom=False, top=False)
        ax.tick_params(axis="x", which="major", bottom=True, top=True)
    ax_p.set_xticklabels(t["unit"], rotation=90, fontsize=8)
    fig.align_ylabels((ax_v, ax_p))
    handles = [Line2D([], [], marker="o", ms=5.5, mfc=COMPOSITION_COLOURS[c], mec="black",
                      mew=0.6, ls="none") for c in series]
    # legend in one row, its top just below the axis title
    fig.canvas.draw()
    below = ax_p.xaxis.label.get_window_extent().transformed(fig.transFigure.inverted()).y0
    fig.legend(handles, list(series.values()), loc="upper center", ncol=4,
               bbox_to_anchor=(0.5, below - 0.004), fontsize=9.5, frameon=True,
               fancybox=False, edgecolor="black", framealpha=1.0,
               handletextpad=0.2, columnspacing=1.4)
    fig.savefig(OUT / "Figure_5.png")
    fig.savefig(OUT / "Figure_5.pdf")
    plt.close(fig)
    return fig


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
    fig.savefig(OUT / "Figure_3.png")
    fig.savefig(OUT / "Figure_3.pdf")
    plt.close(fig)
    print("\nndays:", ndays, "| peak hours:",
          [int(h) for h in np.argsort(mean)[-3:]])


if __name__ == "__main__":
    set_mpl()
    fig_validity()
    fig_diurnal()
    fig_use()
    fig_composition()
