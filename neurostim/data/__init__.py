"""Transcribed primary datasets.

Values in :mod:`neurostim.materials` are single constants read from papers. This package
holds the underlying *data* instead -- the individual experimental points -- so that a
criterion fitted to them can be plotted against the evidence rather than asserted.
"""

from . import (
    asanuma1976,
    butterwick2007,
    cogan2016,
    current_distribution,
    elwassif2006,
    gabriel1996,
    iso14708_3,
    mccreery1990,
    mccreery1995,
    mccreery2010,
    riedy_walter1996,
    ta2o5_capacitor,
)
from .mccreery1990 import TABLE_I, DamagePoint, local_charge_density_uC_cm2

__all__ = [
    "TABLE_I",
    "DamagePoint",
    "asanuma1976",
    "butterwick2007",
    "cogan2016",
    "current_distribution",
    "elwassif2006",
    "gabriel1996",
    "iso14708_3",
    "local_charge_density_uC_cm2",
    "mccreery1990",
    "mccreery1995",
    "mccreery2010",
    "riedy_walter1996",
    "ta2o5_capacitor",
]
