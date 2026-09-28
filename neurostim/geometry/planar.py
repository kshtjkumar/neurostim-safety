"""Planar electrode geometries: disc, ring (annulus) and rectangle.

All three are treated as flush-mounted in an otherwise insulating plane bounding a
semi-infinite conducting half-space, which is the standard idealisation behind the
Newman (1966) access-resistance result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..units import um_to_m
from .base import (
    Electrode,
    Environment,
    _check_conductivity,
    _check_environment,
    _check_positive,
)


@dataclass(frozen=True)
class DiscElectrode(Electrode):
    """A flat circular electrode flush with an insulating plane.

    Only the exposed face contributes area. Access resistance is Newman's exact
    primary-current-distribution result for a disc, ``R = 1/(4*sigma*a)``.

    ``environment="full_space"`` and ``stands_in_for`` exist for the presets that use a
    disc of the right *area* to represent a different physical electrode (physics M5,
    ledger 21). A full-space disc takes the equal-area sphere for its access resistance
    and the ``4 pi`` field. Either setting makes the resistance an approximation, and
    :meth:`describe` says so rather than printing "(exact)" beside a note that says
    "modelled as an equal-area disc".
    """

    diameter_um: float
    material: str = "Pt"
    environment: Environment = "half_space"
    stands_in_for: str = ""
    """The physical electrode this disc stands in for by area, or empty for a real disc."""

    def __post_init__(self) -> None:
        _check_positive("diameter_um", self.diameter_um)
        _check_environment(self.environment)

    largest_dimension_kind = "diameter"

    @property
    def radius_um(self) -> float:
        """Disc radius in micrometres."""
        return self.diameter_um / 2.0

    def _enclosing_radius_um(self) -> float:
        return self.radius_um

    @property
    def area_um2(self) -> float:
        return math.pi * self.radius_um**2

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        if self.environment == "full_space":
            return super().access_resistance_ohm(sigma_S_per_m)
        _check_conductivity(sigma_S_per_m)
        return 1.0 / (4.0 * sigma_S_per_m * um_to_m(self.radius_um))

    @property
    def access_resistance_is_exact(self) -> bool:
        return self.environment == "half_space" and not self.stands_in_for

    @property
    def substitute_name(self) -> str:
        if self.stands_in_for and self.environment == "half_space":
            return f"equal-area disc for {self.stands_in_for}"
        if self.stands_in_for:
            return f"equal-area sphere for {self.stands_in_for}"
        return super().substitute_name

    def dimensions(self) -> dict[str, float]:
        return {"diameter": self.diameter_um}


@dataclass(frozen=True)
class RingElectrode(Electrode):
    """An annular electrode, e.g. a ring contact or the rim of a guide cannula.

    Constructed as ``RingElectrode(outer_diameter_um, inner_diameter_um, material)``.

    Access resistance has no simple exact form for an annulus, so the equal-area disc
    substitution from :class:`~neurostim.geometry.base.Electrode` is used. It
    **overestimates** the resistance, and the error grows as the ring thins. Among plane
    shapes of equal area the disc has the least capacity and therefore the most spreading
    resistance (Polya & Szego 1951), so the substitution is an upper bound: conservative
    for the compliance budget. For a ring 200 um across and 1 um wide it is 50 634 ohm,
    against about 11 682 ohm from the thin-ring asymptote, 4.33x high (ledger 10: this
    docstring used to state the direction backwards).
    """

    outer_diameter_um: float
    inner_diameter_um: float
    material: str = "Pt"
    environment: Environment = "half_space"

    def __post_init__(self) -> None:
        _check_environment(self.environment)
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

    largest_dimension_kind = "outer diameter"

    def _enclosing_radius_um(self) -> float:
        return self.outer_diameter_um / 2.0

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

    Access resistance uses the equal-area disc substitution, which **overestimates** it
    by an amount that grows with aspect ratio. Spreading resistance is set by the largest
    linear dimension, not by ``sqrt(area)``, and the disc is the most resistive plane shape
    of a given area (Polya & Szego 1951). Against the exact elliptic disc of the same area
    and aspect, ``K(e) / (2 pi sigma a)``, the substitution is 1.03x high at aspect 2,
    1.34x at 10 and 2.10x at 50. An upper bound, conservative for the compliance budget
    (ledger 10: this docstring used to state the direction backwards).
    """

    width_um: float
    length_um: float
    material: str = "Pt"
    environment: Environment = "half_space"

    def __post_init__(self) -> None:
        _check_environment(self.environment)
        _check_positive("width_um", self.width_um)
        _check_positive("length_um", self.length_um)

    @property
    def area_um2(self) -> float:
        return self.width_um * self.length_um

    largest_dimension_kind = "diagonal"

    def _enclosing_radius_um(self) -> float:
        return math.hypot(self.width_um, self.length_um) / 2.0

    @property
    def aspect_ratio(self) -> float:
        """Long side divided by short side; 1.0 for a square."""
        return max(self.width_um, self.length_um) / min(self.width_um, self.length_um)

    def dimensions(self) -> dict[str, float]:
        return {"width": self.width_um, "length": self.length_um}
