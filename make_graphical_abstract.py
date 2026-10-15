"""Graphical abstract for the CSCEE submission.

Journal spec: 1328 x 531 px (w x h) or proportionally more, readable at 13 x 5 cm.
The canvas is 6.5 x 2.6 in (2.5:1), saved as vector SVG and PDF. Typography comes from
scientific.mplstyle; the cooking-rhythm curve is the mean of Figure 3's daily
profiles, via the same helper, so the two cannot drift apart.

    python3 make_graphical_abstract.py   # -> figures/graphical_abstract.{svg,pdf}
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Polygon, Arc, FancyArrowPatch, Wedge, PathPatch
from matplotlib.path import Path

from make_figures import OUT, STYLE, daily_profiles

# Colour pair checked for lightness band, chroma, colour-vision-deficiency and
# normal-vision separation, and 3:1 contrast on white. DATA marks things that
# work or carry data; FAIL marks the silent failure. Everything else is neutral.
DATA, FAIL = "#2A65B0", "#A87B12"
INK, INK2, MUTED = "#1f1f1f", "#4d4d4d", "#8f8c86"
RULE = "#d8d5ce"
CONCRETE, SOIL, SLATE, STEEL = "#cfcac0", "#8c7b63", "#4a5361", "#6b6b6b"
FLAME_OUT, FLAME_IN = "#E07B2E", "#F5C542"   # illustrative only, not data

W, H = 6.5, 2.6                               # inches; all drawing is in inch coordinates
COLS = [(0.12, 2.00), (2.28, 4.08), (4.36, 6.38)]


def flame(ax, x, y, h, w):
    """Symmetric flame on a burner at (x, y): round base, pointed tip; outer and inner tongue."""
    for scale, col in ((1.0, FLAME_OUT), (0.58, FLAME_IN)):
        hh, ww = h * scale, w * scale
        tip = (x, y + hh)
        verts = [tip, (x + ww * 0.15, y + hh * 0.65), (x + ww * 0.55, y + hh * 0.40), (x + ww * 0.42, y + hh * 0.14),
                 (x + ww * 0.30, y - hh * 0.04), (x - ww * 0.30, y - hh * 0.04), (x - ww * 0.42, y + hh * 0.14),
                 (x - ww * 0.55, y + hh * 0.40), (x - ww * 0.15, y + hh * 0.65), tip, tip]
        codes = [Path.MOVETO] + [Path.CURVE4] * 9 + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), facecolor=col, edgecolor="none", zorder=5))


def badge(ax, xc, yc, ok):
    """Round status badge: white tick (ok) or cross on the status colour."""
    ax.add_patch(plt.Circle((xc, yc), 0.085, facecolor=DATA if ok else FAIL, edgecolor="white", lw=1.2, zorder=6))
    if ok:
        ax.plot([xc - 0.040, xc - 0.010, xc + 0.045], [yc + 0.002, yc - 0.032, yc + 0.035],
                color="white", lw=1.6, solid_capstyle="round", solid_joinstyle="round", zorder=7)
    else:
        for sgn in (1, -1):
            ax.plot([xc - 0.033, xc + 0.033], [yc - 0.033 * sgn, yc + 0.033 * sgn],
                    color="white", lw=1.6, solid_capstyle="round", zorder=7)


def panel_pilot(ax):
    """Digester -> monitor -> stove, solar-powered, cellular link."""
    gy = 0.98                                             # ground level
    ax.add_patch(Rectangle((0.12, gy - 0.07), 1.90, 0.07, facecolor=SOIL, edgecolor="none", alpha=0.35))
    ax.plot([0.12, 2.02], [gy, gy], color=SOIL, lw=1.0)
    ax.add_patch(Wedge((0.58, gy), 0.44, 0, 180, facecolor=CONCRETE, edgecolor=MUTED, lw=0.7))
    ax.text(0.58, gy + 0.16, "digester", fontsize=9, ha="center", va="center", color=INK2)
    # gas line: dome top -> monitor -> into the stove body
    ax.plot([0.58, 0.58, 1.40], [gy + 0.44, gy + 0.62, gy + 0.62], color=STEEL, lw=1.5, solid_capstyle="round")
    ax.add_patch(FancyBboxPatch((1.00, gy + 0.535), 0.30, 0.17, boxstyle="round,pad=0,rounding_size=0.03",
                                facecolor=DATA, edgecolor="none", zorder=4))
    ax.text(1.15, gy + 0.47, "monitor", fontsize=9, ha="center", va="top", color=INK)
    # solar panel on a mast above the monitor, and the cellular link
    ax.plot([1.15, 1.15], [gy + 0.705, gy + 1.00], color=MUTED, lw=0.8)
    ax.add_patch(Polygon([[0.97, gy + 1.00], [1.29, gy + 1.00], [1.35, gy + 1.15], [1.03, gy + 1.15]],
                         facecolor=SLATE, edgecolor="none"))
    for r in (0.07, 0.13):
        ax.add_patch(Arc((1.33, gy + 0.72), 2 * r, 2 * r, theta1=15, theta2=75, color=INK2, lw=0.9))
    # stove: legs, body, burner head with flame on top
    sx, bw = 1.76, 0.40
    for dx in (-0.15, 0.15):
        ax.plot([sx + dx, sx + dx], [gy, gy + 0.36], color=STEEL, lw=1.1)
    ax.add_patch(FancyBboxPatch((sx - bw / 2, gy + 0.36), bw, 0.20, boxstyle="round,pad=0,rounding_size=0.02",
                                facecolor=STEEL, edgecolor="none", zorder=3))
    ax.plot([1.40, 1.46, 1.46, sx - bw / 2], [gy + 0.62, gy + 0.62, gy + 0.46, gy + 0.46],
            color=STEEL, lw=1.5, solid_joinstyle="round")
    ax.add_patch(Rectangle((sx - 0.08, gy + 0.56), 0.16, 0.035, facecolor=INK2, edgecolor="none", zorder=4))
    flame(ax, sx, gy + 0.60, 0.26, 0.16)
    ax.text(sx, gy + 0.46, "stove", fontsize=8.5, ha="center", va="center", color="white", zorder=6)
    for i, line in enumerate([r"20 households, Kiambu, Kenya", r"6 months of gas-use monitoring",
                              r"solar power, cellular link"]):
        ax.text(0.12, 0.66 - 0.23 * i, line, fontsize=9, va="top", color=INK if i < 2 else INK2)


def panel_worked(fig, ax):
    """Two headline numbers and the measured cooking rhythm (mean of Figure 3's daily profiles).

    The volume is the median of the per-household median daily volumes behind
    Figure 4 (make_stats.py, "[Feasibility, Fig. 4 top]").
    """
    x0 = COLS[1][0]
    for y, big, small, dx in [(1.90, r"17/20", r"units usable,\\83\,\% completeness", 0.90),
                              (1.37, r"1.35\,m$^3$", r"median daily\\gas volume", 1.12)]:
        ax.text(x0, y, rf"\textbf{{{big}}}", fontsize=19, va="center")
        ax.text(x0 + dx, y, rf"\begin{{tabular}}{{@{{}}l}}{small}\end{{tabular}}", fontsize=9,
                va="center", color=INK2)
    mean = daily_profiles().mean(axis=0).values
    axd = fig.add_axes([(x0 + 0.02) / W, 0.30 / H, 1.76 / W, 0.50 / H])
    axd.plot(np.arange(24), mean, color=DATA, lw=1.4)
    axd.set_xlim(0, 23); axd.set_ylim(0, mean.max() * 1.2)
    axd.set_xticks([0, 6, 12, 18]); axd.set_xticklabels([r"0\,h", r"6\,h", r"12\,h", r"18\,h"], fontsize=8.5)
    axd.set_yticks([]); axd.minorticks_off()
    axd.tick_params(axis="x", top=False, length=2.5)
    axd.tick_params(axis="y", left=False, right=False)
    ax.text(x0, 0.93, r"measured daily cooking rhythm", fontsize=9, va="center")


def panel_lessons(ax):
    """Two one-line lessons, then the silent failure: sensor measuring nothing, radio still sending."""
    x0 = COLS[2][0]
    ax.text(x0, 1.90, r"Firmware fault needed correction", fontsize=9.5, va="center")
    ax.text(x0, 1.58, r"SIM credit ran out: 2 data gaps", fontsize=9.5, va="center")
    ax.text(x0, 1.18, r"One failed unit, for 5 months:", fontsize=9.5, va="center")
    iy = 0.62                                             # icon centre line
    lx = x0 + 0.45                                        # flow monitor on its gas line
    ax.plot([lx - 0.36, lx + 0.36], [iy, iy], color=STEEL, lw=1.6, solid_capstyle="round")
    ax.add_patch(FancyBboxPatch((lx - 0.21, iy - 0.12), 0.42, 0.24, boxstyle="round,pad=0,rounding_size=0.04",
                                facecolor=DATA, edgecolor="none", zorder=4))
    badge(ax, lx + 0.21, iy + 0.12, ok=False)
    ax.text(lx, iy - 0.30, r"no measurements", fontsize=9, ha="center", va="center", color=INK2)
    ax.add_patch(FancyArrowPatch((x0 + 0.95, iy), (x0 + 1.23, iy), arrowstyle="-|>", mutation_scale=11,
                                 color=MUTED, lw=1.2))
    rx = x0 + 1.60                                        # radio mast
    ax.plot([rx, rx], [iy - 0.20, iy + 0.06], color=INK2, lw=1.6, solid_capstyle="round")
    ax.add_patch(plt.Circle((rx, iy + 0.08), 0.03, facecolor=INK2, edgecolor="none"))
    for rr in (0.10, 0.17):
        for th1, th2 in ((-45, 45), (135, 225)):
            ax.add_patch(Arc((rx, iy + 0.08), 2 * rr, 2 * rr, theta1=th1, theta2=th2, color=INK2, lw=1.1))
    badge(ax, rx + 0.19, iy + 0.18, ok=True)
    ax.text(rx, iy - 0.30, r"packets arriving", fontsize=9, ha="center", va="center", color=INK2)


def graphical_abstract():
    plt.style.use(["default", str(STYLE)])
    plt.rcParams.update({"figure.constrained_layout.use": False,   # fixed 2.5:1 canvas
                         "savefig.bbox": "standard"})
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    for (x0, x1), t in zip(COLS, ["The pilot", "What worked", "What dMRV must handle"]):
        ax.text(x0, H - 0.16, rf"\textbf{{{t}}}", fontsize=11.5, va="top", ha="left")
        ax.plot([x0, x1], [H - 0.46, H - 0.46], color=RULE, lw=0.8)
    panel_pilot(ax)
    panel_worked(fig, ax)
    panel_lessons(ax)
    for ext in ("svg", "pdf"):
        fig.savefig(OUT / f"graphical_abstract.{ext}", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    graphical_abstract()
