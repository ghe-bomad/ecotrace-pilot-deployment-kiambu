# figures

The paper's figures, numbered as in the manuscript.

| figure | produced by |
|---|---|
| `Figure_1.{png,pdf}` | drawn with Claude Design (Anthropic): map of the 20 installation sites, cropped to Kiambu County, with latitude and longitude and OpenStreetMap boundaries, from the authors' GPS records with site positions jittered to protect household privacy. Household GPS is not published, so no code here regenerates it. |
| `Figure_2.{png,pdf}` | `../scripts/make_figures.py` `fig_validity` (data validity per unit-day) |
| `Figure_3.{png,pdf}` | `../scripts/make_figures.py` `fig_diurnal` (one household's daily use rhythm) |
| `Figure_4.{png,pdf}` | `../scripts/make_figures.py` `fig_use` (daily gas volume, top, and cooking duration, bottom, per household; the two units that did not measure all gas use of the household in red) |
| `Figure_5.{png,pdf}` | `../scripts/make_figures.py` `fig_composition` (reference gas composition per household digester: CH4, CO2 and the balance to 100 vol-% as stacked bars, top; H2S before and after the filter, joined by arrows, bottom) |
| `graphical_abstract.{svg,pdf}` | `../scripts/make_graphical_abstract.py` (journal graphical abstract, vector) |

The generated figures are committed as the paper versions; re-running
`scripts/make_figures.py` or `scripts/make_graphical_abstract.py` overwrites them.
