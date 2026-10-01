# figures

Rendered figures for the installation paper.

| figure | produced by |
|---|---|
| `Figure_1.{png,pdf}` | `../make_figures.py` (Figure 1, data validity per unit-day) |
| `Figure_2.{png,pdf}` | `../make_figures.py` (Figure 2, one household's use rhythm) |
| `Figure_3.{png,pdf}` | `../make_figures.py` (Figure 3, daily gas-use duration per household) |
| `fig_coverage.{png,pdf}` | `../make_figures.py` (supplementary: telemetry completeness; Figure 1 in earlier versions) |
| `fig_diurnal.png` | legacy render of Figure 2 |
| `graphical_abstract.{svg,pdf}` | `../make_graphical_abstract.py` (journal graphical abstract, 13 x 5 cm, vector) |
| `installation_sites_22.png` | produced manually — the 22 installation sites in Kiambu County; household GPS is not published, so no code here regenerates it. `installation_sites_20.png` is the 20-site version of the same manually produced map. |

The generated figures are committed as the paper versions; re-running
`make_figures.py` overwrites them.
