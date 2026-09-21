"""Electrode geometry base class.

An electrode contributes three things to the safety and field calculations:

1. **Geometric surface area** -- normalises charge into charge density, which is one of
   the two axes of the Shannon criterion and the basis of every published
   charge-injection limit.
2. **Access (spreading) resistance** -- the ohmic resistance from the electrode surface
   out into bulk tissue, which sets the compliance voltage a stimulator must supply.
3. **A characteristic radius** -- the length scale the point-source field and activation
   models fall back on when the exact geometry has no closed-form solution.

Real surface area is deliberately *not* modelled. Roughness factors are electrode- and
process-specific; assuming one would silently inflate every limit. Where a published
limit is normalised to real area (Cogan 2008 marks these), applying it to a geometric
area computed here is conservative for smooth electrodes and wrong for porous ones.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

from ..units import um2_to_cm2, um_to_m


class Electrode(ABC):
    """Base class for all electrode geometries.

    Subclasses provide :attr:`area_um2` and may override
    :meth:`access_resistance_ohm` where an exact analytic solution exists.

    Deliberately *not* a dataclass: concrete geometries declare their own fields with
    ``material`` last, so that positional construction reads
    ``RingElectrode(outer, inner, material)`` rather than putting the material first.
    """

    material: str

    # --- geometry ------------------------------------------------------------

    @property
    @abstractmethod
    def area_um2(self) -> float:
        """Geometric (electrochemically exposed) surface area in square micrometres."""

    @property
    def area_cm2(self) -> float:
        """Geometric surface area in square centimetres."""
        return um2_to_cm2(self.area_um2)

    @property
    def equivalent_radius_um(self) -> float:
        """Radius of a disc having the same geometric area.

        Used as the characteristic length scale by the field and access-resistance
        models when a geometry has no exact closed form.
        """
        return math.sqrt(self.area_um2 / math.pi)

    # --- electrical ----------------------------------------------------------

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        """Ohmic access (spreading) resistance into bulk tissue, in ohms.

        The default implementation substitutes an equal-area disc and applies Newman's
        primary-current-distribution result ``R = 1/(4*sigma*a)`` (Newman 1966).
        Subclasses with an exact solution override this.

        The default tissue conductivity of 0.35 S/m is the homogeneous grey-matter value
        used by Elwassif et al. (2006).
        """
        _check_conductivity(sigma_S_per_m)
        a_m = um_to_m(self.equivalent_radius_um)
        return 1.0 / (4.0 * sigma_S_per_m * a_m)

    @property
    def access_resistance_is_exact(self) -> bool:
        """Whether :meth:`access_resistance_ohm` is exact or an equal-area substitution."""
        return False

    # --- reporting -----------------------------------------------------------

    @property
    def shape_name(self) -> str:
        """Human-readable shape name."""
        return type(self).__name__.replace("Electrode", "")

    def dimensions(self) -> dict[str, float]:
        """Defining dimensions in micrometres, for reports and serialisation."""
        return {}

    def describe(self) -> str:
        """One-line human-readable summary."""
        dims = ", ".join(f"{k}={v:g} um" for k, v in self.dimensions().items())
        exact = "exact" if self.access_resistance_is_exact else "equal-area disc approx."
        return (
            f"{self.shape_name} [{self.material}] {dims} -> "
            f"area {self.area_cm2:.4g} cm^2, "
            f"R_access {self.access_resistance_ohm():.0f} ohm ({exact})"
        )


def _check_positive(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if value <= 0:
        raise ValueError(f"{name} must be > 0 um, got {value!r}")


def _check_conductivity(sigma_S_per_m: float) -> None:
    if not math.isfinite(sigma_S_per_m) or sigma_S_per_m <= 0:
        raise ValueError(
            f"Tissue conductivity must be a positive finite S/m value, "
            f"got {sigma_S_per_m!r}"
        )
