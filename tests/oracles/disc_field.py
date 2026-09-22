"""The exact potential around a disc electrode flush in an insulating plane.

A disc of radius ``a`` held at uniform potential in the surface of an insulating plane,
injecting current ``I`` into a half-space of conductivity ``sigma``, has the closed-form
solution (oblate spheroidal coordinates; Newman 1966 gives the resistance, the potential
follows from the same separation)::

    V(r) = (2/pi) * I * R_access * arcsin(a/r)      for r >= a,  R_access = 1/(4 sigma a)

Two things make this the right oracle for the space-convention question.

**It pins the resistance and the field together -- through**
:func:`disc_potential_V`, **which takes the conductivity and computes R itself.** At the
rim, ``arcsin(1) = pi/2``, so ``V(a) = I * R_access`` exactly -- not approximately,
bit-for-bit in IEEE arithmetic. Any change that moves the access resistance without moving
the field, or the reverse, breaks it.

That holds only for the self-contained form. :func:`disc_surface_potential_V` takes R as an
argument and is the primitive the closed form is written in; a pin built on it is blind to
an error in R that the package shares, because the two move together. Measured, not
asserted: hand it an R that is wrong by a factor of two and today's unrepaired full-space
field model scores **0.999983** against it -- the very number that is supposed to mean the
field model has been repaired. So a test of the space convention must call
:func:`disc_potential_V`, and pin the package's access resistance separately against
:func:`newman_disc_resistance_ohm`. ``tests/test_oracles.py`` does both.

**It separates the two errors that currently cancel.** The package's field model returns a
full-space ``4 pi`` geometry factor for a disc, which is documented as flush in an
insulating plane and therefore injects into a half-space. Far from the disc the exact
solution tends to the point source, so the ratio at ``r = 100a`` isolates the factor:

======================  ================  ==========
form                    V(100a) / exact   verdict
======================  ================  ==========
``I/(4 pi sigma r)``    0.499992          today
``I/(2 pi sigma r)``    0.999983          correct
======================  ================  ==========

The residual 1.7e-5 is the genuine near-field departure of a disc from a point source at
a hundred radii, not a discrepancy to be tuned away. A test that demanded 1.0000 at the
rim instead would force ``1/(4 sigma a) -> 1/(2 pi sigma a)``, a 57 % error in the access
resistance manufactured by the test: the point source is the disc's asymptote, not its
surface field, and the legitimate ratio between them is exactly ``pi/2``.

Nothing here imports ``neurostim``.
"""

from __future__ import annotations

import math


def disc_surface_potential_V(
    current_A: float, access_resistance_ohm: float, radius_m: float, distance_m: float
) -> float:
    """Potential at ``distance_m`` from the centre of a flush disc, on its axis of symmetry.

    ``distance_m`` must be at least ``radius_m``; inside the disc the potential is uniform
    at ``I * R`` and the arcsin form does not apply.
    """
    if radius_m <= 0.0:
        raise ValueError(f"radius_m must be > 0, got {radius_m!r}")
    if distance_m < radius_m:
        raise ValueError(
            f"distance_m must be >= radius_m ({radius_m!r}); the disc surface is "
            f"equipotential at I*R inside that"
        )
    return (2.0 / math.pi) * current_A * access_resistance_ohm * math.asin(radius_m / distance_m)


def newman_disc_resistance_ohm(conductivity_S_per_m: float, radius_m: float) -> float:
    """``R = 1/(4 sigma a)`` -- Newman 1966, the half-space flush disc."""
    if conductivity_S_per_m <= 0.0:
        raise ValueError(
            f"conductivity_S_per_m must be > 0, got {conductivity_S_per_m!r}"
        )
    if radius_m <= 0.0:
        raise ValueError(f"radius_m must be > 0, got {radius_m!r}")
    return 1.0 / (4.0 * conductivity_S_per_m * radius_m)


def disc_potential_V(
    current_A: float, conductivity_S_per_m: float, radius_m: float, distance_m: float
) -> float:
    """Potential at ``distance_m`` from a flush disc, with R derived from the conductivity.

    The form every pin should use. It is :func:`disc_surface_potential_V` composed with
    :func:`newman_disc_resistance_ohm`, and the composition is the point: the access
    resistance is the oracle's own, so a package whose R is wrong cannot make its field
    model agree by supplying that R to both sides of the comparison.
    """
    resistance_ohm = newman_disc_resistance_ohm(conductivity_S_per_m, radius_m)
    return disc_surface_potential_V(current_A, resistance_ohm, radius_m, distance_m)


def point_source_potential_V(
    current_A: float,
    conductivity_S_per_m: float,
    distance_m: float,
    *,
    geometry_factor: float,
) -> float:
    """``V = I / (factor * sigma * r)``. ``factor`` is ``4 pi`` full-space, ``2 pi`` half."""
    return current_A / (geometry_factor * conductivity_S_per_m * distance_m)


FULL_SPACE_FACTOR = 4.0 * math.pi
HALF_SPACE_FACTOR = 2.0 * math.pi
