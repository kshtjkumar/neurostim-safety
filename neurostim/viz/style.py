"""Publication figure style and export helpers.

Follows the standard high-impact-journal contract: 7 pt sans-serif body text, editable
text in vector output (``svg.fonttype = "none"``, ``pdf.fonttype = 42``), no top or
right spines, no legend frames, and hairline axes.

Palette policy
--------------
One restrained palette per figure: a **neutral** family for reference lines and context,
a **signal** family for the quantity being argued about, and green/amber/red reserved
strictly as *directional* cues for pass / caution / fail. Safety status is the one place
in this package where red-green carries meaning, so it is not spent on ordinary
categorical series. The categorical family is colour-blind safe and stays legible in
greyscale.

Export
------
:func:`save_publication` writes SVG, PDF and TIFF together at 600 dpi and never opens the
file it wrote.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

from .. import _repro

MM = 1.0 / 25.4
"""Millimetres to inches, for journal column widths."""

SINGLE_COLUMN_MM = 89.0
"""Nature single-column width."""

DOUBLE_COLUMN_MM = 183.0
"""Nature double-column width."""

PALETTE = {
    # neutral family: context, reference lines, unhighlighted series
    "ink": "#1b1f24",
    "grey": "#57606a",
    "mid_grey": "#8c959f",
    "light_grey": "#d0d7de",
    # signal family: the quantity under argument
    "signal": "#2b5d8c",
    "signal_light": "#7aa6c8",
    "accent": "#5d3f8c",
    # directional cues only
    "pass": "#1a7f37",
    "caution": "#9a6700",
    "fail": "#b62324",
}

STATUS_COLOURS = {
    "PASS": PALETTE["pass"],
    "CAUTION": PALETTE["caution"],
    "FAIL": PALETTE["fail"],
    "NOT_EVALUATED": PALETTE["mid_grey"],
}

CATEGORICAL = (
    PALETTE["signal"],
    PALETTE["accent"],
    "#8c6d1f",
    "#1f6f6f",
    PALETTE["grey"],
    "#a34a7f",
)
"""Colour-blind-safe categorical sequence for material or geometry comparisons."""

RC_PARAMS = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "font.size": 7,
    "axes.labelsize": 7,
    "axes.titlesize": 7.5,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "legend.fontsize": 6.5,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
    "axes.edgecolor": PALETTE["ink"],
    "axes.labelcolor": PALETTE["ink"],
    "text.color": PALETTE["ink"],
    "xtick.color": PALETTE["ink"],
    "ytick.color": PALETTE["ink"],
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "lines.linewidth": 1.1,
    "lines.markersize": 3.5,
    "legend.frameon": False,
    "figure.dpi": 150,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.transparent": False,
    "axes.grid": False,
}


def apply_style() -> None:
    """Apply the publication rcParams globally."""
    mpl.rcParams.update(RC_PARAMS)


def figure(
    width_mm: float = SINGLE_COLUMN_MM, height_mm: float = 60.0, **kwargs
) -> plt.Figure:
    """Create a figure sized in millimetres, with the publication style applied."""
    apply_style()
    return plt.figure(figsize=(width_mm * MM, height_mm * MM), **kwargs)


def subplots(
    nrows: int = 1,
    ncols: int = 1,
    width_mm: float = SINGLE_COLUMN_MM,
    height_mm: float = 60.0,
    **kwargs,
):
    """``plt.subplots`` with millimetre sizing and the publication style applied."""
    apply_style()
    return plt.subplots(
        nrows, ncols, figsize=(width_mm * MM, height_mm * MM), **kwargs
    )


def panel_label(ax, label: str, *, dx: float = -0.20, dy: float = 1.09) -> None:
    """Place a bold panel letter in axes-fraction coordinates."""
    ax.text(
        dx,
        dy,
        label,
        transform=ax.transAxes,
        fontsize=8.5,
        fontweight="bold",
        va="top",
        ha="left",
        color=PALETTE["ink"],
    )


IMAGE_EXTENSIONS = frozenset({"svg", "pdf", "tif", "tiff", "png", "eps", "ps", "jpg", "jpeg"})
"""Suffixes :func:`save_publication` treats as a format to replace, not part of the name."""


def save_publication(
    fig: plt.Figure,
    path: str | Path,
    *,
    dpi: int = 600,
    formats: tuple[str, ...] = ("svg", "pdf", "tiff"),
    close: bool = False,
) -> list[Path]:
    """Save a figure in publication formats and return the written paths.

    ``path`` may carry an image extension or not; one it carries is replaced by each
    requested format. Anything else after a dot is part of the name: ``"shannon_k1.5"``
    writes ``shannon_k1.5.svg``. It used to be stripped too, so ``"shannon_k1.5"`` and
    ``"shannon_k1.8"`` both wrote ``shannon_k1.svg`` and the second destroyed the first
    (ledger 58). SVG and PDF keep text editable for a typesetter; TIFF is the raster
    fallback at ``dpi``, written as LZW-compressed RGB: matplotlib's own TIFF is
    uncompressed RGBA, 47 MB for the four-panel summary, above journal upload caps and
    with the alpha channel journals reject (ledgers 61/M12, 87). The raster is rendered
    losslessly and flattened, so the pixels are the ones matplotlib drew. The written files
    are never opened.

    Output is byte-reproducible: element ids are salted from a fixed string rather than a
    per-process ``uuid4``, matplotlib's own version is kept out of the file, and the
    embedded date follows ``SOURCE_DATE_EPOCH`` when it is set. See :mod:`neurostim._repro`.
    """
    base = Path(path)
    if base.suffix.lower().lstrip(".") in IMAGE_EXTENSIONS:
        base = base.with_suffix("")
    base.parent.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    with mpl.rc_context({"svg.hashsalt": _repro.SVG_HASH_SALT}):
        for fmt in formats:
            out = base.with_name(f"{base.name}.{fmt}")
            if fmt in ("tif", "tiff"):
                _save_tiff(fig, out, dpi)
            else:
                metadata = _repro.VECTOR_METADATA.get(fmt)
                fig.savefig(out, format=fmt, dpi=dpi, bbox_inches="tight", metadata=metadata)
            written.append(out)
    if close:
        plt.close(fig)
    return written


def _save_tiff(fig: plt.Figure, out: Path, dpi: int) -> None:
    """``fig`` as an LZW-compressed RGB TIFF at ``dpi`` (ledgers 61/M12, 87)."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    buffer.seek(0)
    with Image.open(buffer) as image:
        image.convert("RGB").save(out, format="TIFF", compression="tiff_lzw", dpi=(dpi, dpi))
