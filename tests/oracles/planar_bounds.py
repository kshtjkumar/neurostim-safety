"""Exact and near-exact access resistances of non-circular flush planar electrodes.

The package gives a ring and a rectangle the access resistance of an equal-area disc.
Which way that errs is a theorem, not a judgement. Among all plane shapes of a given
area, the disc has the smallest electrostatic capacity (Polya & Szego, *Isoperimetric
Inequalities in Mathematical Physics*, 1951). A flush electrode's half-space spreading
resistance is ``2 eps0 / (sigma C)``, so the disc has the *largest* resistance, and the
equal-area disc overestimates every other shape. The docstrings said the opposite for
both geometries (ledger 10).

Two independent references, neither importing ``neurostim``:

* :func:`elliptic_disc_resistance_ohm`: exact. ``C = 4 pi eps0 a / K(e)`` for an
  elliptic disc of semi-major axis ``a`` gives ``R = K(e) / (2 pi sigma a)``, with ``K``
  the complete elliptic integral of the first kind, computed here by the
  arithmetic-geometric mean. ``K(0) = pi/2`` recovers Newman's disc ``1/(4 sigma a)``.
* :func:`thin_ring_resistance_ohm`: the thin-ring capacity ``C = 2 pi^2 eps0 D /
  ln(8D/d)`` for a ring of diameter ``D``, with a flat strip of width ``w`` taken as a
  wire of diameter ``d = w/2``. Asymptotic, good for ``w << D``, and so used only for the
  direction and rough size of the error, not as an exact value.
"""

from __future__ import annotations

import math


def complete_elliptic_k(modulus: float) -> float:
    """``K(e)`` by the arithmetic-geometric mean: ``pi / (2 AGM(1, sqrt(1 - e^2)))``."""
    if not 0.0 <= modulus < 1.0:
        raise ValueError(f"modulus must be in [0, 1), got {modulus!r}")
    a, b = 1.0, math.sqrt(1.0 - modulus**2)
    for _ in range(64):
        a, b = (a + b) / 2.0, math.sqrt(a * b)
        if abs(a - b) <= 1e-16 * a:
            break
    return math.pi / (2.0 * a)


def elliptic_disc_resistance_ohm(
    conductivity_S_per_m: float, semi_major_m: float, semi_minor_m: float
) -> float:
    """Exact half-space access resistance of a flush elliptic disc."""
    if not 0.0 < semi_minor_m <= semi_major_m:
        raise ValueError("need 0 < semi_minor_m <= semi_major_m")
    modulus = math.sqrt(1.0 - (semi_minor_m / semi_major_m) ** 2)
    return complete_elliptic_k(modulus) / (
        2.0 * math.pi * conductivity_S_per_m * semi_major_m
    )


def thin_ring_resistance_ohm(
    conductivity_S_per_m: float, diameter_m: float, strip_width_m: float
) -> float:
    """Asymptotic half-space resistance of a thin flush ring, ``ln(8D/d) / (sigma pi^2 D)``."""
    wire_diameter_m = strip_width_m / 2.0
    return math.log(8.0 * diameter_m / wire_diameter_m) / (
        conductivity_S_per_m * math.pi**2 * diameter_m
    )
