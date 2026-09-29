# figures

Rendered figures for the installation paper.

| figure | produced by |
|---|---|
| `fig_coverage.png` | `../make_figures.py` (Figure 1, telemetry completeness) |
| `fig_diurnal.png` | `../make_figures.py` (Figure 2, one household's use rhythm) |
| `graphical_abstract.{svg,pdf}` | `../make_graphical_abstract.py` (journal graphical abstract, 13 x 5 cm, vector) |
| `installation_sites_22.png` | produced manually — the 22 installation sites in Kiambu County; household GPS is not published, so no code here regenerates it. `installation_sites_20.png` is the 20-site version of the same manually produced map. |

The two generated figures are committed as the paper versions; re-running
`make_figures.py` overwrites them.
