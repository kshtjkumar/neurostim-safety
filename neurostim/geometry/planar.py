"""Planar electrode geometries: disc, ring (annulus) and rectangle.

All three are treated as flush-mounted in an otherwise insulating plane bounding a
semi-infinite conducting half-space, which is the standard idealisation behind the
Newman (1966) access-resistance result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..units import um_to_m
from .base import Electrode, _check_conductivity, _check_positive


@dataclass(frozen=True)
class DiscElectrode(Electrode):
    """A flat circular electrode flush with an insulating plane.

    Only the exposed face contributes area. Access resistance is Newman's exact
    primary-current-distribution result for a disc, ``R = 1/(4*sigma*a)``.
    """

    diameter_um: float
    material: str = "Pt"

    def __post_init__(self) -> None:
        _check_positive("diameter_um", self.diameter_um)

    @property
    def radius_um(self) -> float:
        """Disc radius in micrometres."""
        return self.diameter_um / 2.0

    @property
    def area_um2(self) -> float:
        return math.pi * self.radius_um**2

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        _check_conductivity(sigma_S_per_m)
        return 1.0 / (4.0 * sigma_S_per_m * um_to_m(self.radius_um))

    @property
    def access_resistance_is_exact(self) -> bool:
        return True

    def dimensions(self) -> dict[str, float]:
        return {"diameter": self.diameter_um}


@dataclass(frozen=True)
class RingElectrode(Electrode):
    """An annular electrode, e.g. a ring contact or the rim of a guide cannula.

    Constructed as ``RingElectrode(outer_diameter_um, inner_diameter_um, material)``.

    Access resistance has no simple exact form for an annulus, so the equal-area disc
    substitution from :class:`~neurostim.geometry.base.Electrode` is used. For a thin
    ring this *underestimates* the resistance, because a thin ring concentrates current
    at two edges rather than spreading it over a filled disc of the same area.
    """

    outer_diameter_um: float
    inner_diameter_um: float
    material: str = "Pt"

    def __post_init__(self) -> None:
        _check_positive("outer_diameter_um", self.outer_diameter_um)
        if not math.isfinite(self.inner_diameter_um) or self.inner_diameter_um < 0:
            raise ValueError(
                f"inner_diameter_um must be a finite value >= 0, "
                f"got {self.inner_diameter_um!r}"
            )
        if self.inner_diameter_um >= self.outer_diameter_um:
            raise ValueError(
                f"inner_diameter_um ({self.inner_diameter_um} um) must be smaller than "
                f"outer_diameter_um ({self.outer_diameter_um} um); a ring with "
                f"inner >= outer has zero or negative area"
            )

    @property
    def area_um2(self) -> float:
        ro = self.outer_diameter_um / 2.0
        ri = self.inner_diameter_um / 2.0
        return math.pi * (ro**2 - ri**2)

    @property
    def wall_thickness_um(self) -> float:
        """Radial width of the annulus."""
        return (self.outer_diameter_um - self.inner_diameter_um) / 2.0

    def dimensions(self) -> dict[str, float]:
        return {
            "outer_diameter": self.outer_diameter_um,
            "inner_diameter": self.inner_diameter_um,
        }


@dataclass(frozen=True)
class RectangularElectrode(Electrode):
    """A rectangular pad, e.g. a lithographically patterned surface contact.

    Access resistance uses the equal-area disc substitution. The error grows with
    aspect ratio: a long thin strip has a higher access resistance than the equal-area
    disc because current crowds at its long edges.
    """

    width_um: float
    length_um: float
    material: str = "Pt"

    def __post_init__(self) -> None:
        _check_positive("width_um", self.width_um)
        _check_positive("length_um", self.length_um)

    @property
    def area_um2(self) -> float:
        return self.width_um * self.length_um

    @property
    def aspect_ratio(self) -> float:
        """Long side divided by short side; 1.0 for a square."""
        return max(self.width_um, self.length_um) / min(self.width_um, self.length_um)

    def dimensions(self) -> dict[str, float]:
        return {"width": self.width_um, "length": self.length_um}
