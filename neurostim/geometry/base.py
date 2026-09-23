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
from typing import Literal

from ..units import um2_to_cm2, um_to_m

Environment = Literal["half_space", "full_space"]
"""Which space the electrode injects into (fix plan D4).

``half_space``: flush in an insulating plane, so current fills a half-space -- disc,
ring, rectangle, hemisphere. ``full_space``: surrounded by tissue on every side -- sphere,
cylindrical band, microwire. It sets both the point-source field factor (``2 pi`` or
``4 pi``) and which equal-area substitute stands in for a geometry with no exact access
resistance (Newman's disc or the sphere). One property read by both, so the compliance
budget and the field cannot disagree about the same electrode again (ledger 17).
"""

ENVIRONMENTS: tuple[Environment, ...] = ("half_space", "full_space")


class Electrode(ABC):
    """Base class for all electrode geometries.

    Subclasses provide :attr:`area_um2` and may override
    :meth:`access_resistance_ohm` where an exact analytic solution exists.

    Deliberately *not* a dataclass: concrete geometries declare their own fields with
    ``material`` last, so that positional construction reads
    ``RingElectrode(outer, inner, material)`` rather than putting the material first.
    """

    material: str
    environment: Environment
    """See :data:`Environment`. An instance field with a class-appropriate default, not a
    class property, because presets model immersed electrodes as equal-area discs
    (physics M5)."""

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

        The characteristic length scale of a half-space geometry with no exact closed
        form, and the one the Butterwick size correction and the field-panel start use.
        """
        return math.sqrt(self.area_um2 / math.pi)

    @property
    def equivalent_sphere_radius_um(self) -> float:
        """Radius of a sphere having the same geometric area, ``4 pi a^2 = A``."""
        return math.sqrt(self.area_um2 / (4.0 * math.pi))

    # --- electrical ----------------------------------------------------------

    def access_resistance_ohm(self, sigma_S_per_m: float = 0.35) -> float:
        """Ohmic access (spreading) resistance into bulk tissue, in ohms.

        The default is an equal-area substitute chosen by :attr:`environment`. A
        half-space geometry takes Newman's flush disc, ``R = 1/(4 sigma a)`` (Newman 1966).
        A full-space geometry takes the sphere, ``R = 1/(4 pi sigma a)`` with
        ``4 pi a^2 = A``. Subclasses with an exact solution override this.

        **Why the sphere, not the disc, for an immersed body** (ledger 20). The disc is a
        half-space result; tissue on every side roughly halves the resistance again. A
        converged finite-difference solve of a band on an insulating shaft
        (``tests/oracles/fd_band``) puts the clinical DBS contact at 335.1 ohm. The
        equal-area sphere gives 329.5 (-1.7 %) and the half-space disc 517.5 (+54 %). The
        sphere stays within 2 % from aspect 0.39 to 2.0 and degrades to +17 % at aspect 10.
        The immersed-cylinder ``ln(2L/r)`` form proposed instead is negative below aspect
        0.25 and worse than the sphere everywhere measured (ledger 80), so it is not used.
        No exact band formula exists here, which is ledger 16, documented rather than fixed.

        The default tissue conductivity of 0.35 S/m is the homogeneous grey-matter value
        used by Elwassif et al. (2006).
        """
        _check_conductivity(sigma_S_per_m)
        if self.environment == "full_space":
            a_m = um_to_m(self.equivalent_sphere_radius_um)
            return 1.0 / (4.0 * math.pi * sigma_S_per_m * a_m)
        a_m = um_to_m(self.equivalent_radius_um)
        return 1.0 / (4.0 * sigma_S_per_m * a_m)

    @property
    def access_resistance_is_exact(self) -> bool:
        """Whether :meth:`access_resistance_ohm` is exact or an equal-area substitution."""
        return False

    @property
    def substitute_name(self) -> str:
        """The equal-area body :meth:`access_resistance_ohm` substitutes, when inexact."""
        return "equal-area sphere" if self.environment == "full_space" else "equal-area disc"

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
        exact = (
            "exact" if self.access_resistance_is_exact else f"{self.substitute_name} approx."
        )
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


def _check_environment(value: str) -> None:
    if value not in ENVIRONMENTS:
        raise ValueError(
            f"environment must be one of {ENVIRONMENTS}, got {value!r}"
        )
