"""Three-dimensional electrode geometries: cylindrical bands, microwire tips, spheres.

The sphere and hemisphere have exact closed-form access resistances and are the only
geometries here for which the point-source field model is strictly self-consistent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from ..units import um_to_m
from .base import Electrode, _check_conductivity, _check_positive

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

    def __post_init__(self) -> None:
        _check_positive("diameter_um", self.diameter_um)
        _check_positive("height_um", self.height_um)

    @property
    def area_um2(self) -> float:
        return math.pi * self.diameter_um * self.height_um

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        """Equal-area disc substitution.

        No compact exact solution exists for a band on an insulating cylinder. For the
        near-unity aspect ratios of clinical DBS contacts the substitution is
        reasonable; for a tall narrow band it degrades.
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
    """

    diameter_um: float
    exposed_length_um: float = 0.0
    tip_shape: TipShape = "flat"
    cone_height_um: float | None = None
    material: str = "Pt"

    def __post_init__(self) -> None:
        _check_positive("diameter_um", self.diameter_um)
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
        if self.exposed_length_um == 0 and self.tip_shape == "flat":
            # A flat-tipped wire with no shaft exposure is just a disc; allowed, but
            # the caller probably wants DiscElectrode.
            pass

    @property
    def radius_um(self) -> float:
        """Wire radius in micrometres."""
        return self.diameter_um / 2.0

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

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        _check_conductivity(sigma_S_per_m)
        return 1.0 / (2.0 * math.pi * sigma_S_per_m * um_to_m(self.radius_um))

    @property
    def access_resistance_is_exact(self) -> bool:
        return True

    def dimensions(self) -> dict[str, float]:
        return {"diameter": self.diameter_um}
