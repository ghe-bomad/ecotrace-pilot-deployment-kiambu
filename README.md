# ecoTrace biogas-sensor pilot: installation and feasibility, Kiambu County, Kenya

[![DOI 10.5281/zenodo.22233280](badges/doi.svg)](https://doi.org/10.5281/zenodo.22233280)
[![Licence Apache 2.0](badges/license.svg)](LICENSE)

Figures, statistics and their generating code for the installation and
feasibility pilot paper: a feasibility assessment of low-cost, manufacturer-independent
digital MRV for household biogas, from the ~6-month, 20-household Kiambu pilot.
The paper argues that low-cost independent monitoring can capture operational
status and use rhythms but is not yet a turnkey route to calibration-free
absolute quantification.

The manuscript prose lives in the authors' private paper repository; only the
code and the final figures are here. The survey analysis, the cohort use-rhythm
analysis and the feasibility check against literature production envelopes
belong to the companion technical paper, *ecoTrace biogas-sensor pilot, Kiambu
County, Kenya: sensor, calibration and CFD* — cited here by name only, not by
repository path. This repository's own `fig_diurnal` is narrower: one
household's normalised, shape-only use rhythm, not the cohort analysis.

## Contents

| path | what |
|---|---|
| `make_figures.py` | generator for `Figure_2` (data validity), `Figure_3` (use rhythm), `Figure_4` (daily gas use per household: volume on top, cooking duration below) and `Figure_5` (reference gas composition per digester); `Figure_1`, the site map, was drawn with Claude Design |
| `validity.py` | the four-check data-validity classification behind Figure 2 and its quoted counts |
| `make_stats.py` | reproduces every number the paper quotes that is not read off a figure |
| `test_volumes.py` | tests for the daily-volume calculation behind Figure 4 and the shared unit order (`python3 -m pytest`) |
| `test_composition.py` | tests for the gas-composition table behind Figure 5 |
| `make_graphical_abstract.py` | generator for the journal's graphical abstract |
| `scientific.mplstyle` | figure style (LaTeX serif, Okabe-Ito, 600 dpi) |
| `figures/` | the paper's figures, including the site map drawn with Claude Design (Figure 1) |
| `scripts/get_data.sh` | clones and derives the companion dataset |
| `badges/` | the README badges, committed as SVG rather than fetched at render time |

## The figures

- **`Figure_1`** (`.png`, `.pdf`): map of the 20 installation sites, cropped to
  Kiambu County, with latitude and longitude, on OpenStreetMap boundaries. Site
  positions are from the authors' GPS records, jittered to protect household
  privacy. Drawn with Claude Design (Anthropic), not by code in this
  repository: household GPS is not part of the published dataset, so the map
  cannot be regenerated from public data.
- **`Figure_2`** (`fig_validity`): the validity class of every household unit-day.
  `validity.py` applies four checks in order: link (connectivity heartbeats
  received), data (one-minute sensor records received), sensor health (no more
  than 20 flow-sensor reset messages a day) and use (at least 3 min a day in
  measuring runs of three or more consecutive minutes with corrected flow at or
  above the 2 L/min deadband; see the `validity.py` docstring for every
  threshold and the order of the checks). The thresholds were set from this
  fleet and are heuristics; "valid" means the sensor was alive and measuring,
  not that its readings are accurate. Units are in ascending number, as in
  Figure 4. The three units that fail the inclusion criterion (SN_01012,
  SN_01018, SN_01023; a unit is usable only if it was still returning sensor
  records in the final week of the pilot) are marked with an asterisk and
  excluded from the quoted statistics. This set is not the same as the
  technical paper's `EXCLUDE_SENSORS`, which drops SN_01005 and SN_01010 (ILRI
  research reactors, out of scope here too) plus SN_01012 and SN_01018, but
  keeps SN_01023.
- **`Figure_3`** (`fig_diurnal`): one household's normalised daily use rhythm.
  Each day is normalised to 100%, so the figure is shape-only and carries no
  absolute volumes. Reads the data repository's derived CSVs, which contain
  only state-0 (normal measuring) rows with the swap-corrected flow.
- **`Figure_4`** (`fig_use`): daily gas use per usable household on valid days.
  The top panel is the daily gas volume; the bottom panel is the cooking
  duration (see `validity.py`). The volume comes from the dataset's
  `flow_zero_cal` column (the flow with each unit's zero-flow offset removed;
  see the dataset's `docs/field_correction.md` §7) and uses the dataset's volume
  definition: one-minute measuring rows at or above 0.5 L/min (the dataset's
  no-flow gate) plus `gap_fill_L`, the unmeasured gas the dataset fills in next
  to rows in use, summed per UTC day, the same day key `validity.py` uses. The
  interiors of gaps longer than one sleep cycle are not filled. `make_stats.py`
  reports the filled share. Flows and volumes are in standard litres at 20 °C and
  101.325 kPa, as in the dataset.
- **`Figure_5`** (`fig_composition`): the reference gas composition of each
  household digester, from the dataset's `biogas_composition.json` (Dräger
  X-am 8000 spot readings, treated as ground truth). Top: CH4 and CO2 in vol-%.
  Bottom: H2S in ppm in the raw gas and after the household's H2S filter,
  where each was measured, on one vertical per unit; an arrow joins the two
  where both were measured and the markers do not overlap. H2S readings logged as `"max"` are drawn at the
  analyser's 100 ppm upper range limit (dashed line). CO and NH3 are not shown.
  The CH4, CO2 and O2 values come from the raw-gas reading, or from the
  after-filter reading for the four units measured only there.

## Getting the data

```bash
bash scripts/get_data.sh
```

This clones the companion dataset repository (`ecotrace-pilot-data-kiambu`) at
the revision pinned in `DATA_VERSION`, or updates an existing checkout, then
builds its derived data. `make_figures.py` locates that repository via the
`ECOTRACE_DATA` environment variable, if set, or otherwise a sibling checkout
`../ecotrace-pilot-data-kiambu`.

## Running

```bash
pip install -r requirements.txt
python3 make_figures.py     # -> figures/Figure_2 to Figure_5 (.png, .pdf); Figure_1 is drawn outside this repo
python3 -m pytest           # tests for the Figure 4 volume, the unit order and the Figure 5 table
python3 make_stats.py       # prints the paper's quoted statistics, labelled by where they appear
python3 make_graphical_abstract.py   # -> figures/graphical_abstract.{svg,pdf}
```

`make_graphical_abstract.py` draws its cooking-rhythm curve with the same
`daily_profiles` helper as Figure 3, so the two cannot drift apart. It needs
LaTeX, like `make_figures.py`.

`make_stats.py` imports the loaders and constants from `make_figures.py`, so the
unit sets, pilot window and completeness definition are shared, and it asserts
that the hand-listed excluded units are exactly those the inclusion rule
excludes. It needs no LaTeX.

**A system LaTeX installation is also required.** `scientific.mplstyle` sets
`text.usetex = True`, so matplotlib shells out to LaTeX for every label; this is
not a pip dependency and `pip install -r requirements.txt` will not supply it.
Install TeX Live (Linux), MacTeX (macOS) or MiKTeX (Windows) with `amsmath` and
`dvipng` on `PATH`. To render without LaTeX at the cost of the paper typography,
comment out the `text.usetex` line in `scientific.mplstyle`.

## Citation

Cite this repository and, separately, the dataset it depends on:

- this repository — [10.5281/zenodo.22233280](https://doi.org/10.5281/zenodo.22233280)
- companion dataset — [10.5281/zenodo.22232789](https://doi.org/10.5281/zenodo.22232789)

Both are concept DOIs and always resolve to the newest version. Use the **version
DOI** of the release you actually ran, so your analysis is pinned to the exact
code and data you used; each Zenodo record lists it.

## Licence

[Apache-2.0](LICENSE). The figures under `figures/` are outputs of that code
and released under the same terms.

## A note on privacy

This repository contains no household data. It reads raw telemetry (Parquet)
and derived, de-identified CSVs from the dataset repository at runtime; it
never reads the household survey.
