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

Convergence (regenerated at ledger 127). Nodes cluster at the band edge from both sides,
with the first cell ``h/250``, ``h/500`` and ``h/1000`` over three levels. Each level is
extrapolated in far-box size (``1/L``), then the three levels are extrapolated by
Richardson; the observed order is 1.58-1.70. The Richardson value is what is tabulated.
Its distance from the finest grid is at most 0.31 ohm (0.05 %), and a fourth level
(``h/2000``) lands within 0.06 ohm of it at the clinical aspect. The same solver on
Newman's flush disc reproduces the exact ``1/(4 sigma a)`` to 0.009 %. An independent
axisymmetric FV solve by the Phase 3 reviewer, written separately, agrees to 0.3 % at
every aspect (327.8, 520.6, 473.9 and 653.7 ohm at 1.181, 0.39, 0.5 and 0.2).

**The first table was wrong.** Its radial cells were a fixed fraction of the shaft radius,
so the band edge was under-resolved, and worse as the band shortened: 335.1 ohm at the
clinical aspect and 739.9 at aspect 0.2. It certified an equal-area sphere "within 2 %"
from aspect 0.39 to 2.0 that is really 10 % high at 0.39 (ledger 127).

What it settles
---------------
=========  ========  ===============  ===============  ===============
aspect     FV        eq-sphere        eq-disc          ln(2h/r)
=========  ========  ===============  ===============  ===============
0.200      653.4     800.6 (+22.5%)   1257.6 (+92%)    -399.5
0.390      520.4     573.3 (+10.2%)   900.6 (+73%)     408.3 (-21.5%)
0.500      473.7     506.4  (+6.9%)   795.4 (+68%)     496.4  (+4.8%)
1.000      353.8     358.1  (+1.2%)   562.4 (+59%)     496.4 (+40.3%)
1.181      327.6     329.5  (+0.6%)   517.5 (+58%)     470.7 (+43.7%)
2.000      252.3     253.2  (+0.3%)   397.7 (+58%)     372.3 (+47.6%)
4.000      171.8     179.0  (+4.2%)   281.2 (+64%)     248.2 (+44.5%)
10.00      96.7      113.2 (+17.1%)   177.9 (+84%)     132.1 (+36.6%)
=========  ========  ===============  ===============  ===============

The equal-area sphere is **high at every aspect solved**, so it errs toward a larger
compliance requirement. It is within +1.2 % from aspect 1 to 2 (the clinical contact is
+0.6 %), +7 to +10 % at aspect 0.39-0.5, and +17 to +23 % at the extremes. The half-space
equal-area disc the package used before C3.1 is 58-92 % high. The ``ln(2h/r)/(2 pi sigma
h)`` form proposed as a repair is not rejected for accuracy at every aspect -- at 0.5 it
is 4.8 % against the sphere's 6.9 %. It is rejected because it is negative below aspect
0.25, returns the same 496.4 ohm for two different aspects, is 21.5 % *low*
(anti-conservative) at aspect 0.39, and is 36-48 % high everywhere from aspect 1 upward.
"""

from __future__ import annotations

CONDUCTIVITY_S_PER_M = 0.35
SHAFT_DIAMETER_UM = 1270.0

CLINICAL_DBS_ASPECT = 1.181
"""1500 um band on a 1270 um shaft: the Medtronic 3389 contact."""

FD_BAND_REFERENCE: dict[float, float] = {
    0.200: 653.4,
    0.390: 520.4,
    0.500: 473.7,
    1.000: 353.8,
    1.181: 327.6,
    2.000: 252.3,
    4.000: 171.8,
    10.000: 96.7,
}
"""Aspect ratio (band height / shaft diameter) -> access resistance in ohm."""

CONVERGENCE_SPREAD_OHM = 0.2
"""Distance between the finest grid and the Richardson value at the clinical aspect (0.18)."""
