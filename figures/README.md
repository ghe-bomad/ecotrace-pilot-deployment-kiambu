# figures

The paper's figures, numbered as in the manuscript.

| figure | produced by |
|---|---|
| `Figure_1.png` | produced manually: map of the 20 installation sites in Kiambu County, with site positions jittered to protect household privacy. Household GPS is not published, so no code here regenerates it. |
| `Figure_2.{png,pdf}` | `../make_figures.py` `fig_validity` (data validity per unit-day) |
| `Figure_3.{png,pdf}` | `../make_figures.py` `fig_diurnal` (one household's daily use rhythm) |
| `Figure_4.{png,pdf}` | `../make_figures.py` `fig_use` (daily gas volume, top, and cooking duration, bottom, per household) |
| `graphical_abstract.{svg,pdf}` | `../make_graphical_abstract.py` (journal graphical abstract, vector) |

The generated figures are committed as the paper versions; re-running
`make_figures.py` overwrites them.
