"""Electrode geometries.

Planar geometries (:mod:`~neurostim.geometry.planar`) sit flush in an insulating plane;
volumetric geometries (:mod:`~neurostim.geometry.volumetric`) are immersed in tissue.
Only the disc, sphere and hemisphere carry exact access-resistance solutions; the rest
fall back on an equal-area disc substitution, flagged by
:attr:`Electrode.access_resistance_is_exact`.
"""

from .arrays import ArraySite, ElectrodeArray, grid_array, linear_array
from .base import Electrode
from .planar import DiscElectrode, RectangularElectrode, RingElectrode
from .volumetric import (
    CylindricalBandElectrode,
    HemisphericalElectrode,
    MicrowireElectrode,
    SphericalElectrode,
)

__all__ = [
    "ArraySite",
    "CylindricalBandElectrode",
    "DiscElectrode",
    "Electrode",
    "ElectrodeArray",
    "HemisphericalElectrode",
    "MicrowireElectrode",
    "RectangularElectrode",
    "RingElectrode",
    "SphericalElectrode",
    "grid_array",
    "linear_array",
]
