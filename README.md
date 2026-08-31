# ecoTrace biogas-sensor pilot: installation and feasibility, Kiambu County, Kenya

Figures and figure-generating code for the installation and social-science short
communication: a feasibility assessment of low-cost, manufacturer-independent
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
| `make_figures.py` | self-contained generator for `fig_coverage` and `fig_diurnal` |
| `scientific.mplstyle` | figure style (LaTeX serif, Okabe-Ito, 600 dpi) |
| `figures/` | the rendered figures, including the manually produced site maps |
| `scripts/get_data.sh` | clones and derives the companion dataset |

## The figures

- **`fig_coverage`** (Figure 1): daily telemetry-completeness heatmap, one row
  per device serial, de-identified. Reads raw Parquet from the data repository
  and re-derives what it needs. All 20 household units are plotted; the three
  that fail the inclusion criterion (SN_01012, SN_01018, SN_01023) are drawn
  identically and simply sort to the bottom, but are excluded from the quoted
  statistics. Note this set is not the same as the technical paper's
  `EXCLUDE_SENSORS`: that analysis drops SN_01005 and SN_01010 (ILRI research
  reactors, out of scope here too) plus SN_01012 and SN_01018, but keeps
  SN_01023, which has enough data for the analyses it appears in while being too
  sparse for a coverage statistic. Days before a unit's installation are masked
  and painted warm grey, distinct from the completeness ramp, so "no data" cannot
  read as "low completeness".
- **`fig_diurnal`** (Figure 2): one household's normalised daily use rhythm.
  Each day is normalised to 100%, so the figure is shape-only and carries no
  absolute volumes. Reads the data repository's derived CSVs, which contain
  only state-0 (normal measuring) rows with the swap-corrected flow.
- **`installation_sites_22.png`**: map of the 22 installation sites in Kiambu
  County. Produced manually, not by code in this repository: household GPS is
  not part of the published dataset, so the map cannot be regenerated from
  public data. `installation_sites_20.png` is the 20-site version of the same
  manually produced map.

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
python3 make_figures.py     # -> figures/fig_coverage.png, figures/fig_diurnal.png
```

**A system LaTeX installation is also required.** `scientific.mplstyle` sets
`text.usetex = True`, so matplotlib shells out to LaTeX for every label; this is
not a pip dependency and `pip install -r requirements.txt` will not supply it.
Install TeX Live (Linux), MacTeX (macOS) or MiKTeX (Windows) with `amsmath` and
`dvipng` on `PATH`. To render without LaTeX at the cost of the paper typography,
comment out the `text.usetex` line in `scientific.mplstyle`.

## Citation

Cite this repository via its DOI (see `CITATION.cff`) and, separately, cite the
dataset it depends on. Use the version DOI of the release you actually ran.

## Licence

[Apache-2.0](LICENSE). The figures under `figures/` are outputs of that code
and released under the same terms.

## A note on privacy

This repository contains no household data. It reads raw telemetry (Parquet)
and derived, de-identified CSVs from the dataset repository at runtime; it
never reads the household survey.
