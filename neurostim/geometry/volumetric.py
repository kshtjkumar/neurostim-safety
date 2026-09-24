"""Three-dimensional electrode geometries: cylindrical bands, microwire tips, spheres.

The sphere and hemisphere have exact closed-form access resistances and are the only
geometries here for which the point-source field model is strictly self-consistent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from ..units import um_to_m
from .base import (
    Electrode,
    Environment,
    _check_conductivity,
    _check_environment,
    _check_positive,
)

TipShape = Literal["flat", "hemispherical", "conical"]


@dataclass(frozen=True)
class CylindricalBandElectrode(Electrode):
    """A cylindrical band contact, the standard clinical DBS lead geometry.

    Only the lateral (curved) surface is exposed; the band is a sleeve around an
    insulating shaft, so the end caps do not contribute:
    ``A = pi * d * h``.

    A Medtronic 3389-style contact (1270 um diameter, 1500 um height) gives
    0.0599 cm^2, matching the 0.06 cm^2 quoted for clinical DBS electrodes in
    Cogan (2008) Table 1 footnote b.
    """

    diameter_um: float
    height_um: float
    material: str = "PtIr"
    environment: Environment = "full_space"

    def __post_init__(self) -> None:
        _check_positive("diameter_um", self.diameter_um)
        _check_positive("height_um", self.height_um)
        _check_environment(self.environment)

    @property
    def area_um2(self) -> float:
        return math.pi * self.diameter_um * self.height_um

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        """Equal-area sphere substitution; see :meth:`Electrode.access_resistance_ohm`.

        No compact exact solution exists for a band on an insulating cylinder. Against a
        converged finite-volume solve the sphere is high at every aspect: the clinical 3389
        contact reads 329.5 ohm against 327.6 (+0.6 %), +0.3 to +1.2 % from aspect 1 to 2,
        +7 to +10 % at 0.39-0.5 and +17 to +23 % at the extremes (ledger 127). It replaced
        the half-space equal-area disc, which is 58-92 % high because it assumes tissue on
        one side only (ledger 20).
        """
        return super().access_resistance_ohm(sigma_S_per_m)

    @property
    def aspect_ratio(self) -> float:
        """Height divided by diameter."""
        return self.height_um / self.diameter_um

    def dimensions(self) -> dict[str, float]:
        return {"diameter": self.diameter_um, "height": self.height_um}


@dataclass(frozen=True)
class MicrowireElectrode(Electrode):
    """An insulated microwire with a defined exposed length at the tip.

    Area is the exposed cylindrical shaft plus the tip cap:

    - ``flat``: shaft + a flat disc of the wire cross-section
    - ``hemispherical``: shaft + half a sphere of the wire radius
    - ``conical``: shaft + the lateral surface of a cone of height ``cone_height_um``

    ``exposed_length_um`` is the cylindrical exposure *behind* the tip cap and may be
    zero for a wire exposed only at its very end.

    **Access resistance** (ledger 129). No closed form exists. Against a converged
    finite-volume solve (``scripts/fd_microwire_reference.py``,
    ``tests/oracles/fd_microwire``) the full-space equal-area sphere is within about
    +-1.4 % for a flat tip with 0.25-5 wire radii of exposed shaft (-1.3 % at 2 radii,
    the one mildly low region). It is high and growing for longer exposures: +6.7 % at 10
    radii and +17 % at 20. For a flat tip with **no** shaft the sphere is about 8 % *low*
    (0.159 against about 0.173 in units of ``1/(sigma a)``), which is anti-conservative.
    That one case takes Newman's half-space disc of the tip, ``1/(4 sigma a)`` (0.25), an
    upper bound, instead. Hemispherical and conical tips with no shaft stay on the sphere
    and have **not** been checked against a solve.
    """

    diameter_um: float
    exposed_length_um: float = 0.0
    tip_shape: TipShape = "flat"
    cone_height_um: float | None = None
    material: str = "Pt"
    environment: Environment = "full_space"

    def __post_init__(self) -> None:
        _check_positive("diameter_um", self.diameter_um)
        _check_environment(self.environment)
        if not math.isfinite(self.exposed_length_um) or self.exposed_length_um < 0:
            raise ValueError(
                f"exposed_length_um must be a finite value >= 0, "
                f"got {self.exposed_length_um!r}"
            )
        if self.tip_shape not in ("flat", "hemispherical", "conical"):
            raise ValueError(
                f"tip_shape must be flat, hemispherical or conical, "
                f"got {self.tip_shape!r}"
            )
        if self.tip_shape == "conical":
            if self.cone_height_um is None:
                raise ValueError(
                    "cone_height_um is required when tip_shape='conical'"
                )
            _check_positive("cone_height_um", self.cone_height_um)
        elif self.cone_height_um is not None:
            # It would be silently ignored: a flat or hemispherical tip has no cone, so the
            # area would be the plain wire's whatever height was given (ledger 29).
            raise ValueError(
                f"cone_height_um applies only to tip_shape='conical'; got "
                f"{self.cone_height_um!r} with tip_shape={self.tip_shape!r}"
            )
        if self.exposed_length_um == 0 and self.tip_shape == "flat":
            # A flat-tipped wire with no shaft exposure is just a disc; allowed, but
            # the caller probably wants DiscElectrode.
            pass

    @property
    def radius_um(self) -> float:
        """Wire radius in micrometres."""
        return self.diameter_um / 2.0

    @property
    def _bare_flat_tip(self) -> bool:
        return self.tip_shape == "flat" and self.exposed_length_um == 0.0

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        """The equal-area sphere, except Newman's disc for a bare flat tip (class docstring)."""
        if self._bare_flat_tip:
            _check_conductivity(sigma_S_per_m)
            return 1.0 / (4.0 * sigma_S_per_m * um_to_m(self.radius_um))
        return super().access_resistance_ohm(sigma_S_per_m)

    @property
    def substitute_name(self) -> str:
        if self._bare_flat_tip:
            return "half-space disc (upper bound)"
        return super().substitute_name

    @property
    def shaft_area_um2(self) -> float:
        """Exposed lateral area of the cylindrical shaft."""
        return math.pi * self.diameter_um * self.exposed_length_um

    @property
    def tip_area_um2(self) -> float:
        """Area of the tip cap alone."""
        r = self.radius_um
        if self.tip_shape == "flat":
            return math.pi * r**2
        if self.tip_shape == "hemispherical":
            return 2.0 * math.pi * r**2
        if self.cone_height_um is None:  # pragma: no cover - guarded in __post_init__
            raise ValueError("conical tip requires cone_height_um")
        slant = math.sqrt(r**2 + self.cone_height_um**2)
        return math.pi * r * slant

    @property
    def area_um2(self) -> float:
        return self.shaft_area_um2 + self.tip_area_um2

    def dimensions(self) -> dict[str, float]:
        dims = {
            "diameter": self.diameter_um,
            "exposed_length": self.exposed_length_um,
        }
        if self.tip_shape == "conical" and self.cone_height_um is not None:
            dims["cone_height"] = self.cone_height_um
        return dims

    @property
    def shape_name(self) -> str:
        return f"Microwire({self.tip_shape} tip)"


@dataclass(frozen=True)
class SphericalElectrode(Electrode):
    """A sphere in an unbounded homogeneous medium.

    Both the area and the access resistance ``R = 1/(4*pi*sigma*a)`` are exact, and the
    external potential field is exactly that of a point source of the same total
    current. This makes it the reference geometry for the field and activation models.
    """

    diameter_um: float
    material: str = "Pt"

    def __post_init__(self) -> None:
        _check_positive("diameter_um", self.diameter_um)

    @property
    def radius_um(self) -> float:
        """Sphere radius in micrometres."""
        return self.diameter_um / 2.0

    @property
    def area_um2(self) -> float:
        return 4.0 * math.pi * self.radius_um**2

    @property
    def environment(self) -> Environment:  # type: ignore[override]
        """Always ``full_space``: that is what makes this geometry exact."""
        return "full_space"

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        _check_conductivity(sigma_S_per_m)
        return 1.0 / (4.0 * math.pi * sigma_S_per_m * um_to_m(self.radius_um))

    @property
    def access_resistance_is_exact(self) -> bool:
        return True

    def dimensions(self) -> dict[str, float]:
        return {"diameter": self.diameter_um}


@dataclass(frozen=True)
class HemisphericalElectrode(Electrode):
    """A hemisphere flush with an insulating plane bounding a conducting half-space.

    Exactly half the sphere problem: half the area, twice the access resistance,
    ``R = 1/(2*pi*sigma*a)``.
    """

    diameter_um: float
    material: str = "Pt"

    def __post_init__(self) -> None:
        _check_positive("diameter_um", self.diameter_um)

    @property
    def radius_um(self) -> float:
        """Hemisphere radius in micrometres."""
        return self.diameter_um / 2.0

    @property
    def area_um2(self) -> float:
        return 2.0 * math.pi * self.radius_um**2

    @property
    def environment(self) -> Environment:  # type: ignore[override]
        """Always ``half_space``: flush in the insulating plane, by definition."""
        return "half_space"

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        _check_conductivity(sigma_S_per_m)
        return 1.0 / (2.0 * math.pi * sigma_S_per_m * um_to_m(self.radius_um))

    @property
    def access_resistance_is_exact(self) -> bool:
        return True

    def dimensions(self) -> dict[str, float]:
        return {"diameter": self.diameter_um}
