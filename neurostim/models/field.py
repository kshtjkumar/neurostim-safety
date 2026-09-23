"""Extracellular potential and electric field from a stimulating electrode.

Point-source model
------------------
For a spherical source of total current ``I`` in an unbounded, homogeneous, isotropic
medium of conductivity ``sigma``, the potential outside the sphere is exactly that of a
point source:

.. math::

    V(r) = \\frac{I}{4\\pi\\sigma r}, \\qquad
    E(r) = -\\frac{dV}{dr} = \\frac{I}{4\\pi\\sigma r^{2}}

Any electrode flush with an insulating plane -- disc, ring, rectangle, hemisphere --
sees the same current confined to a half-space, doubling both quantities. Which one
applies is :attr:`~neurostim.geometry.base.Electrode.environment`. For the disc the
half-space point source is the far-field limit of the exact solution
``V(r) = (2/pi) I R arcsin(a/r)``. It is not the surface potential: at ``r = a`` the
disc sits at ``I R``, which is pi/2 times the point source there.

Validity
--------
This is the correct exact solution for a sphere and a good approximation elsewhere at
distances of a few electrode radii or more. Close to a non-spherical electrode it is
wrong in a specific direction: real geometries have current crowding at edges, so a
disc or band produces a higher local field near its rim than this model reports.

Brain tissue is also neither homogeneous nor isotropic. White matter conductivity is
anisotropic by roughly an order of magnitude between along-fibre and cross-fibre
directions, and the encapsulation layer around a chronic implant differs from bulk
tissue. Nothing here models any of that -- for those effects a finite element solution
is required, and :mod:`neurostim.io.fem` provides the import path for one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..geometry.arrays import ElectrodeArray
from ..geometry.base import Electrode

BRAIN_CONDUCTIVITY_S_PER_M = 0.35
"""Package default: the homogeneous brain conductivity used by Elwassif et al. (2006).

Retained as the default because 0.35 S/m is the long-standing convention in the DBS
modelling literature, so results computed with it are comparable with published work.
It is **not** the best-supported value -- see :data:`GREY_MATTER_CONDUCTIVITY_S_PER_M`,
which aggregates 214 measurements. Pass whichever you intend explicitly; every function
here takes ``sigma_S_per_m``.
"""

GREY_MATTER_CONDUCTIVITY_S_PER_M = 0.419
"""Grey-matter low-frequency conductivity, IT'IS Database v4.2 (sd 0.230, n = 214).

About 20 % higher than the 0.35 S/m convention, which lowers access resistance and
therefore the required compliance voltage by roughly the same fraction.
"""

WHITE_MATTER_CONDUCTIVITY_S_PER_M = 0.348
"""White-matter low-frequency conductivity, IT'IS Database v4.2 (sd 0.194, n = 194).

White matter is strongly anisotropic; the IT'IS database tabulates separate along-fibre
and across-fibre values. This isotropic average discards that, and no model in this
package represents anisotropy at all.
"""

BLOOD_CONDUCTIVITY_S_PER_M = 0.662
"""Blood low-frequency conductivity, IT'IS Database v4.2 (sd 0.107, n = 33)."""


def _geometry_factor(electrode: Electrode | None) -> float:
    """``4 pi`` for a full space, ``2 pi`` for a source confined to a half-space.

    Read from :attr:`Electrode.environment`, the same property that picks the access
    resistance, so the field and the compliance budget agree about which space an
    electrode injects into. It used to be ``2 pi`` for the hemisphere alone. Disc, ring and
    rectangle, flush in an insulating plane and given Newman's half-space resistance,
    got a full-space field, so the far field of a disc was exactly half the true value
    (ledger 17). ``None`` is a bare point source in a full space.
    """
    if electrode is not None and electrode.environment == "half_space":
        return 2.0 * math.pi
    return 4.0 * math.pi


def potential_V(
    current_uA: float,
    distance_um: float | np.ndarray,
    sigma_S_per_m: float = BRAIN_CONDUCTIVITY_S_PER_M,
    *,
    electrode: Electrode | None = None,
) -> float | np.ndarray:
    """Extracellular potential at a distance from a point source, in volts.

    Distances at or below zero are rejected: the point-source potential diverges at the
    origin, and returning ``inf`` there would silently propagate into any activation
    estimate built on top of it.
    """
    if sigma_S_per_m <= 0 or not math.isfinite(sigma_S_per_m):
        raise ValueError(f"sigma_S_per_m must be finite and > 0, got {sigma_S_per_m!r}")
    r_m = np.asarray(distance_um, dtype=float) * 1e-6
    if np.any(r_m <= 0):
        raise ValueError(
            "distance_um must be > 0; the point-source potential diverges at r = 0"
        )
    i_A = current_uA * 1e-6
    result = i_A / (_geometry_factor(electrode) * sigma_S_per_m * r_m)
    return float(result) if np.isscalar(distance_um) or result.ndim == 0 else result


def field_V_per_m(
    current_uA: float,
    distance_um: float | np.ndarray,
    sigma_S_per_m: float = BRAIN_CONDUCTIVITY_S_PER_M,
    *,
    electrode: Electrode | None = None,
) -> float | np.ndarray:
    """Radial electric field magnitude at a distance from a point source, in V/m."""
    if sigma_S_per_m <= 0 or not math.isfinite(sigma_S_per_m):
        raise ValueError(f"sigma_S_per_m must be finite and > 0, got {sigma_S_per_m!r}")
    r_m = np.asarray(distance_um, dtype=float) * 1e-6
    if np.any(r_m <= 0):
        raise ValueError(
            "distance_um must be > 0; the point-source field diverges at r = 0"
        )
    i_A = current_uA * 1e-6
    result = i_A / (_geometry_factor(electrode) * sigma_S_per_m * r_m**2)
    return float(result) if np.isscalar(distance_um) or result.ndim == 0 else result


def current_density_A_per_m2(
    current_uA: float,
    distance_um: float | np.ndarray,
    *,
    electrode: Electrode | None = None,
) -> float | np.ndarray:
    """Current density on a shell at the given radius, in A/m^2.

    Independent of conductivity: the current simply spreads over the shell area.
    """
    r_m = np.asarray(distance_um, dtype=float) * 1e-6
    if np.any(r_m <= 0):
        raise ValueError("distance_um must be > 0")
    i_A = current_uA * 1e-6
    result = i_A / (_geometry_factor(electrode) * r_m**2)
    return float(result) if np.isscalar(distance_um) or result.ndim == 0 else result


def distance_for_potential_um(
    current_uA: float,
    target_V: float,
    sigma_S_per_m: float = BRAIN_CONDUCTIVITY_S_PER_M,
    *,
    electrode: Electrode | None = None,
) -> float:
    """Invert :func:`potential_V`: the radius at which the potential equals a target."""
    if target_V <= 0:
        raise ValueError(f"target_V must be > 0, got {target_V!r}")
    i_A = current_uA * 1e-6
    r_m = i_A / (_geometry_factor(electrode) * sigma_S_per_m * target_V)
    return r_m * 1e6


@dataclass(frozen=True)
class FieldProfile:
    """Sampled potential and field along a radial line from the electrode."""

    distance_um: np.ndarray
    potential_V: np.ndarray
    field_V_per_m: np.ndarray
    current_uA: float
    sigma_S_per_m: float

    def describe(self) -> str:
        """One-line summary of the sampled range."""
        return (
            f"Field profile: {self.current_uA:g} uA at sigma = {self.sigma_S_per_m:g} "
            f"S/m, {self.distance_um[0]:g}-{self.distance_um[-1]:g} um, "
            f"V {self.potential_V[0]:.4g} -> {self.potential_V[-1]:.4g} V"
        )


def radial_profile(
    current_uA: float,
    min_distance_um: float,
    max_distance_um: float,
    n_points: int = 200,
    sigma_S_per_m: float = BRAIN_CONDUCTIVITY_S_PER_M,
    *,
    electrode: Electrode | None = None,
    log_spaced: bool = True,
) -> FieldProfile:
    """Sample potential and field over a radial range."""
    if min_distance_um <= 0:
        raise ValueError(f"min_distance_um must be > 0, got {min_distance_um!r}")
    if max_distance_um <= min_distance_um:
        raise ValueError("max_distance_um must exceed min_distance_um")
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")

    if log_spaced:
        r = np.logspace(
            math.log10(min_distance_um), math.log10(max_distance_um), n_points
        )
    else:
        r = np.linspace(min_distance_um, max_distance_um, n_points)

    return FieldProfile(
        distance_um=r,
        potential_V=np.asarray(
            potential_V(current_uA, r, sigma_S_per_m, electrode=electrode)
        ),
        field_V_per_m=np.asarray(
            field_V_per_m(current_uA, r, sigma_S_per_m, electrode=electrode)
        ),
        current_uA=current_uA,
        sigma_S_per_m=sigma_S_per_m,
    )


def array_potential_V(
    array: ElectrodeArray,
    currents_uA: list[float] | np.ndarray,
    points_um: np.ndarray,
    sigma_S_per_m: float = BRAIN_CONDUCTIVITY_S_PER_M,
) -> np.ndarray:
    """Superpose point-source potentials from every site of an array.

    Parameters
    ----------
    points_um:
        Array of shape ``(n_points, 3)`` giving field points in the array's frame.

    Superposition is exact for a linear medium, but it assumes each site behaves as an
    independent point source. That breaks down when sites are close relative to their
    size, because the presence of a neighbouring conductor redistributes current.
    """
    currents = np.asarray(currents_uA, dtype=float)
    if currents.shape != (len(array),):
        raise ValueError(
            f"currents_uA must have one entry per site: expected {len(array)}, "
            f"got {currents.shape}"
        )
    pts = np.asarray(points_um, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(f"points_um must have shape (n, 3), got {pts.shape}")

    total = np.zeros(len(pts), dtype=float)
    for site, current in zip(array.sites, currents, strict=True):
        offset = pts - np.asarray(site.position_um(), dtype=float)
        r = np.linalg.norm(offset, axis=1)
        if np.any(r <= 0):
            raise ValueError(
                f"field point coincides with site {site.label or '?'}; "
                f"the point-source potential diverges there"
            )
        total += np.asarray(
            potential_V(float(current), r, sigma_S_per_m, electrode=site.electrode)
        )
    return total
