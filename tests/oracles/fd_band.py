"""Converged finite-difference access resistance for a band on an insulating shaft.

There is no compact exact solution for a cylindrical band flush in the surface of an
insulating shaft, which is the geometry of every clinical DBS contact, so the only way to
know what the answer is is to solve for it. The table below is that solve. Its generator
is ``scripts/fd_band_reference.py``, which imports no part of ``neurostim``: axisymmetric
finite-volume Laplace, band at ``V = 1``, insulating shaft above and below it, symmetry at
the band's midplane, ``V -> 0`` at the far field.

Conditions: ``sigma = 0.35 S/m``, shaft diameter ``d = 1270 um`` (Medtronic 3389). Aspect
ratio is band height over shaft diameter, so 1.181 is the clinical contact -- 1500 um of
band on a 1270 um shaft.

Convergence. Re-solving the clinical aspect over grids from 300x300 to 700x700 and far
fields from 300x to 3000x the shaft radius gives 334.0 to 336.8 ohm: the value is
335 +/- 1.5 ohm, about +/-0.45 %. Every comparison this table is used for is an error of
2 % or more, so that spread does not reach any conclusion drawn from it.

What it settles
---------------
=========  ========  ===========  =============  ==========
aspect     FD        eq-sphere    eq-disc        ln(2L/r)
=========  ========  ===========  =============  ==========
0.200      739.9     800.6        1257.6         -399.5
0.390      559.8     573.3        900.6          408.3
0.500      502.2     506.4        795.4          496.4
1.000      363.7     358.1        562.4          496.4
1.181      335.1     329.5        517.5          470.7
2.000      255.0     253.2        397.7          372.3
10.00      96.3      113.2        177.9          132.1
=========  ========  ===========  =============  ==========

The equal-area sphere is within 2 % from aspect 0.39 to 2.0 and degrades to 17 % by aspect
10. The equal-area disc the package uses today is high by 40-70 % throughout. The
``ln(2L/r)/(2 pi sigma L)`` form proposed as a repair is *negative* below aspect 0.25,
returns the same 496.4 ohm for two different aspect ratios, and is worse than the sphere
everywhere measured. That is why the plan keeps the sphere and documents the error rather
than substituting a formula that looks more physical.
"""

from __future__ import annotations

CONDUCTIVITY_S_PER_M = 0.35
SHAFT_DIAMETER_UM = 1270.0

CLINICAL_DBS_ASPECT = 1.181
"""1500 um band on a 1270 um shaft: the Medtronic 3389 contact."""

FD_BAND_REFERENCE: dict[float, float] = {
    0.200: 739.9,
    0.390: 559.8,
    0.500: 502.2,
    1.000: 363.7,
    1.181: 335.1,
    2.000: 255.0,
    4.000: 172.1,
    10.000: 96.3,
}
"""Aspect ratio (band height / shaft diameter) -> access resistance in ohm."""

CONVERGENCE_SPREAD_OHM = 1.5
"""Half-width of the value across grid and domain refinement at the clinical aspect."""
