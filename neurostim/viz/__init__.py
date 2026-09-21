"""Publication-quality figures.

:mod:`~neurostim.viz.style` holds the rcParams, palette and export helper;
:mod:`~neurostim.viz.plots` holds the figures, each documenting the claim it defends.
"""

from . import plots, style
from .plots import (
    current_limit_sweep,
    material_comparison,
    radial_field_profile,
    safety_summary,
    shannon_safe_operating_area,
    strength_duration,
    thermal_profile,
)
from .style import (
    CATEGORICAL,
    DOUBLE_COLUMN_MM,
    PALETTE,
    SINGLE_COLUMN_MM,
    STATUS_COLOURS,
    apply_style,
    figure,
    panel_label,
    save_publication,
    subplots,
)

__all__ = [
    "CATEGORICAL",
    "DOUBLE_COLUMN_MM",
    "PALETTE",
    "SINGLE_COLUMN_MM",
    "STATUS_COLOURS",
    "apply_style",
    "current_limit_sweep",
    "figure",
    "material_comparison",
    "panel_label",
    "plots",
    "radial_field_profile",
    "safety_summary",
    "save_publication",
    "shannon_safe_operating_area",
    "strength_duration",
    "style",
    "subplots",
    "thermal_profile",
]
