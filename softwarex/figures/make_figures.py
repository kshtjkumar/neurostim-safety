"""SoftwareX figures for neurostim-safety.

Figure 1 (schematic): sourced inputs -> nine checks -> one floored, traceable limit
(or a refusal) -> every output renders the same assessment.
Figure 2 (quantitative): the package's own safety_summary for a Medtronic 3389-style
DBS contact, 3 mA x 60 us per phase at 130 Hz, in vivo.

Run with the package's environment:  python make_figures.py
Writes SVG + PDF + TIFF (600 dpi) next to this script; opens nothing.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent
MM = 1 / 25.4

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": 7,
})

# One restrained palette: neutral (inputs/outputs), signal (safety core), accent (result).
NEUTRAL, NEUTRAL_EDGE = "#EEF1F4", "#5B6770"
SIGNAL, SIGNAL_EDGE = "#DCE9F5", "#2F5F8A"
ACCENT, ACCENT_EDGE = "#FBE9D7", "#B0651E"
SUPPORT, SUPPORT_EDGE = "#F3F0F7", "#6B5B8A"


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.tiff", dpi=600, bbox_inches="tight",
                pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(OUT / f"{name}.png", dpi=300, bbox_inches="tight")  # for the .docx/.pdf
    plt.close(fig)


def box(ax, x, y, w, h, title, lines, face, edge, title_size=7.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                                facecolor=face, edgecolor=edge, linewidth=0.8))
    ax.text(x + w / 2, y + h - 0.035, title, ha="center", va="top",
            fontsize=title_size, fontweight="bold", color=edge)
    ax.text(x + w / 2, y + h - 0.085, "\n".join(lines), ha="center", va="top",
            fontsize=6.2, linespacing=1.35, color="#222222")


def arrow(ax, x0, y0, x1, y1, color="#444444"):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=8,
                                 linewidth=0.8, color=color, shrinkA=2, shrinkB=2))


def figure_1() -> None:
    fig = plt.figure(figsize=(183 * MM, 78 * MM))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    box(ax, 0.01, 0.42, 0.19, 0.54, "Inputs",
        ["Electrode geometry", "(disc, ring, band, microwire,", "rectangle, sphere, array)",
         "Material (9 built in, or", "a user-measured CIC)", "Protocol: current, pulse",
         "width per phase, rate, train,", "duty, charge recovery",
         "Settings: medium, k, policy,", "compliance, counter electrode"],
        NEUTRAL, NEUTRAL_EDGE)

    box(ax, 0.26, 0.42, 0.25, 0.54, "Safety core: 9 checks",
        ["Shannon criterion", "Material charge-injection limit",
         "Water window (+ DC drift)", "Validated envelope of the fit",
         "Current density (electroporation)", "Microelectrode charge/phase",
         "Chronic degradation", "Charge balance", "Compliance voltage",
         "(+ counter charge injection)"],
        SIGNAL, SIGNAL_EDGE)

    box(ax, 0.57, 0.42, 0.19, 0.54, "Result",
        ["Limiting current: the highest", "amplitude no limit-bearing",
         "check fails, floored so the", "printed value passes",
         "Interval across published", "ranges (Shannon k, CIC band)",
         "PROVISIONAL / INCOMPLETE", "flags", "or a refusal naming the",
         "check when nothing is safe"],
        ACCENT, ACCENT_EDGE)

    box(ax, 0.81, 0.42, 0.18, 0.54, "Outputs",
        ["Text summary (describe)", "PDF report with methods", "and bibliography",
         "JSON + audit record", "(SHA-256 digest of inputs,", "constants and answer)",
         "Batch CSV and sweeps", "Figures (SVG/PDF/TIFF)", "Desktop GUI (PyQt6)"],
        NEUTRAL, NEUTRAL_EDGE)

    box(ax, 0.10, 0.03, 0.80, 0.27, "Supporting layers",
        ["Literature data modules: every constant carries its primary source, page and "
         "measurement conditions (pulse width, polarity, electrolyte, area basis)",
         "Models: Pennes bioheat (steady and transient), access resistance, "
         "strength-duration fits with intervals, current-distance activation",
         "Uncertainty: outward-rounded interval arithmetic   |   "
         "FEM import for external field solutions"],
        SUPPORT, SUPPORT_EDGE)

    y = 0.69
    arrow(ax, 0.20, y, 0.26, y)
    arrow(ax, 0.51, y, 0.57, y)
    arrow(ax, 0.76, y, 0.81, y)
    for x in (0.385, 0.665):
        arrow(ax, x, 0.30, x, 0.42, color=SUPPORT_EDGE)
    save(fig, "figure1_architecture")


def figure_2() -> None:
    from neurostim import SafetyCalculator, StimProtocol, get_preset
    from neurostim.viz import safety_summary

    calc = SafetyCalculator(get_preset("dbs_3389").electrode, StimProtocol(3000, 60, 130, 1),
                            compliance_V=10.0, medium="in_vivo")
    fig, _ = safety_summary(calc)
    save(fig, "figure2_dbs3389_summary")


if __name__ == "__main__":
    figure_1()
    figure_2()
    print("written:", sorted(p.name for p in OUT.iterdir() if p.suffix in {".svg", ".pdf", ".tiff", ".png"}))
