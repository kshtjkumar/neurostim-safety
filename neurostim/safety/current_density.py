"""Current density, and the edge concentration a geometric average hides.

Why this exists separately from charge density
----------------------------------------------
Charge density governs the electrochemistry at the interface and the Shannon
tissue-damage criterion. **Current** density governs a different failure mode:
electroporation of cells close to the electrode, and it is the quantity Butterwick
et al. (2007) found to determine irreversible retinal damage, with a threshold that
varies with both pulse width and pulse frequency (via Cogan et al. 2016).

This package computes charge density everywhere and, until now, never computed current
density at all. That is a gap in coverage, not a small one: two protocols with identical
charge per phase and identical charge density can differ several-fold in current density
if their pulse widths differ.

The threshold
-------------
:mod:`neurostim.data.butterwick2007` supplies the damage threshold: it falls as
``t^-0.5`` with pulse width, is independent of electrode size above 300 um, rises as
``d^-2`` below 200 um, and saturates after about 50 pulses. Below 200 um the ``d^-2``
extension sits under the small-electrode currents the paper measured, and the module
records both (ledger 77, S-13). The pulse-count relief was measured on a 1 mm pipette, so
below 200 um the saturated threshold is used at every count (ledger 154).

That threshold was measured on chick chorioallantoic membrane and chick retina, verified
on porcine retina. Applying it to cortex is an extrapolation **across preparation**, so
the check reports a comparison and a margin rather than a pass/fail verdict. The authors
themselves note their sustained membrane threshold is close to what McCreery et al.
measured on cat cortex, which is encouraging but is not the same as validation.

The primary current distribution
--------------------------------
For a disc electrode held at uniform potential against a semi-infinite medium, the
primary (purely ohmic, start-of-pulse) current distribution is

.. math::

    \\frac{J(r)}{J_{avg}} = \\frac{1}{2\\sqrt{1 - (r/a)^{2}}}

which follows from normalising ``J(r) = C/\\sqrt{1-(r/a)^2}`` so that its integral over
the disc is the total current. Two consequences:

- the **centre** of the disc runs at **half** the average current density;
- the density **diverges at the rim**, so the geometric average always understates the
  local peak on a non-recessed electrode.

The fraction of the disc area operating above the average follows analytically:
``J/J_avg > 1`` requires ``r/a > sqrt(3)/2``, giving ``1 - 3/4 =`` **25 %**.

That is an independent derivation, and it lands within half a percent of the **25.6 %**
Kuncel & Grill (2004) obtained by finite element modelling of a cylindrical DBS contact.
Two different geometries and two different methods agreeing this closely is good evidence
the edge effect is real and about this size.

**Only a disc has these numbers** (ledger 18). They used to be printed for every
geometry. A sphere, and a hemisphere flush in its plane, have a *uniform* primary
distribution: ``J = I/A`` everywhere, no edge and no divergence. A ring, rectangle, band
or microwire does crowd at its own edges, but its centre ratio and fraction above average
are not the disc's. No closed form for them is used here, so the result says the edges
crowd and gives no number. :func:`primary_distribution` classifies an electrode, and the
Butterwick comparison, which uses the average, is unaffected by the classification.

Mitigations, from the sources
-----------------------------
Recessing the electrode into its carrier, or flaring the recess, reduces the edge
concentration (Shannon 1992). Reaction kinetics also moderate it as the pulse proceeds:
activation overpotentials push the distribution from the primary form toward a more
uniform secondary form, more so at longer pulse widths and higher current densities
(Cogan et al. 2016). A perfectly non-polarisable electrode, or a saline-filled pipette,
retains the primary distribution throughout and is correspondingly worse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..data import butterwick2007

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..geometry.base import Electrode

Distribution = Literal["disc", "uniform", "edge"]
"""The primary current distribution of a geometry, as far as this package can state it."""

DISC_CENTRE_RATIO = 0.5
"""``J(0)/J_avg`` for a disc under the primary current distribution."""

DISC_FRACTION_ABOVE_AVERAGE = 0.25
"""Fraction of a disc's area above its own average current density.

Derived analytically from the primary distribution. Kuncel & Grill (2004) obtained
25.6 % by finite element modelling of a cylindrical DBS contact -- a close independent
agreement across different geometry and method.
"""

DBS_CLINICAL_REFERENCE_A_PER_CM2 = 0.0993
"""Average current density modelled for a clinical DBS contact at 3 V.

Kuncel & Grill (2004), 1.26 mm x 1.5 mm contact. A reference point for scale, **not** a
damage threshold.
"""


def primary_distribution(electrode: Electrode | None) -> Distribution:
    """Which primary current distribution ``electrode`` has.

    ``"disc"`` for a real flush disc, and for ``None`` (the pre-C3.2 behaviour of a caller
    that names no geometry). ``"uniform"`` for a sphere and a hemisphere. ``"edge"`` for
    everything else, including a disc that stands in for another shape by area: it
    crowds at its edges by an amount no closed form here gives.
    """
    from ..geometry.planar import DiscElectrode
    from ..geometry.volumetric import HemisphericalElectrode, SphericalElectrode

    if electrode is None:
        return "disc"
    if isinstance(electrode, SphericalElectrode | HemisphericalElectrode):
        return "uniform"
    if isinstance(electrode, DiscElectrode) and electrode.access_resistance_is_exact:
        return "disc"
    return "edge"


def average_current_density_A_per_cm2(current_uA: float, area_cm2: float) -> float:
    """Geometric-average current density during the leading phase."""
    if not math.isfinite(area_cm2) or area_cm2 <= 0:
        raise ValueError(f"area_cm2 must be finite and > 0, got {area_cm2!r}")
    if not math.isfinite(current_uA):
        raise ValueError(f"current_uA must be finite, got {current_uA!r}")
    return (current_uA * 1e-6) / area_cm2


def disc_ratio_at_radius(fraction_of_radius: float) -> float:
    """``J(r)/J_avg`` on a disc at a given fraction of its radius.

    Diverges at the rim, so ``fraction_of_radius`` must be strictly below 1. This is a
    property of the idealised primary distribution rather than a physical infinity:
    reaction kinetics and finite electrode edges bound it in reality.
    """
    if not 0.0 <= fraction_of_radius < 1.0:
        raise ValueError(
            f"fraction_of_radius must be in [0, 1), got {fraction_of_radius!r}; "
            f"the primary distribution diverges at the rim"
        )
    return 0.5 / math.sqrt(1.0 - fraction_of_radius**2)


def disc_ratio_at_area_fraction(area_fraction: float) -> float:
    """``J/J_avg`` exceeded by the outermost ``area_fraction`` of a disc.

    ``disc_ratio_at_area_fraction(0.25)`` returns 1.0, which is the statement that the
    outer quarter of a disc runs above its own average.
    """
    if not 0.0 < area_fraction <= 1.0:
        raise ValueError(f"area_fraction must be in (0, 1], got {area_fraction!r}")
    # Area beyond r/a = u is 1 - u^2, so u = sqrt(1 - area_fraction).
    return disc_ratio_at_radius(math.sqrt(1.0 - area_fraction))


@dataclass(frozen=True)
class CurrentDensityResult:
    """Current density of each phase, with the geometric peak factor.

    Both phases, since ledger 4. A return phase of width ``W*r`` carries ``I*r_a/r``, so
    a quarter-width return phase runs at four times the leading amplitude through the same
    area -- and the package evaluated only the leading one, returning bit-identical
    answers for a symmetric protocol and one with ``return_phase_ratio = 0.2`` whose
    return phase draws 5000 uA.

    The return phase is compared against the Butterwick threshold **at its own width**,
    because that is the pulse it is. It is not simply worse than the leading phase: the
    threshold rises as roughly ``t^-0.5`` while the amplitude rises as ``1/r``, so the two
    partly cancel and which phase binds is arithmetic rather than assumption.
    """

    current_uA: float
    area_cm2: float
    average_A_per_cm2: float
    pulse_width_us: float
    edge_concentrates: bool
    fraction_above_average: float | None
    """Share of the surface above the average: 0.25 for a disc, 0.0 for a uniform
    distribution, ``None`` where the geometry crowds at edges by an unquantified amount."""
    centre_ratio: float | None
    """``J(centre)/J_avg``: 0.5 for a disc, 1.0 for a uniform distribution, else ``None``."""
    threshold: butterwick2007.ThresholdComparison | None = None
    return_phase_current_uA: float = 0.0
    return_phase_width_us: float = 0.0
    return_A_per_cm2: float = 0.0
    return_threshold: butterwick2007.ThresholdComparison | None = None
    distribution: Distribution = "disc"
    """See :func:`primary_distribution`."""

    @property
    def has_return_phase(self) -> bool:
        """Whether a second phase delivers current at all.

        False for a monophasic pulse and for a biphasic one that recovers no charge --
        both have a return phase carrying zero current, which has no density and no
        threshold, and whose zero width a ``t ** -n`` power law cannot take.
        """
        return self.return_phase_current_uA > 0.0 and self.return_phase_width_us > 0.0

    @property
    def peak_A_per_cm2(self) -> float:
        """Highest average current density reached by either phase."""
        return max(self.average_A_per_cm2, self.return_A_per_cm2)

    @property
    def binding_phase(self) -> str:
        """``'leading'`` or ``'return'``: the phase closest to its own threshold.

        Not the phase with the higher density. The two phases are compared against
        different thresholds, so the larger density can be the safer one.
        """
        if self.return_threshold is None or self.threshold is None:
            return "leading"
        return (
            "return"
            if self.return_threshold.margin < self.threshold.margin
            else "leading"
        )

    @property
    def binding_threshold(self) -> butterwick2007.ThresholdComparison | None:
        """The comparison for :attr:`binding_phase`; the verdict is taken from this."""
        if self.binding_phase == "return":
            return self.return_threshold
        return self.threshold

    @property
    def relative_to_dbs_clinical(self) -> float:
        """Ratio to the clinical DBS reference point; scale only, not a limit."""
        return self.average_A_per_cm2 / DBS_CLINICAL_REFERENCE_A_PER_CM2

    def ratio_at_area_fraction(self, area_fraction: float) -> float:
        """Peak factor over the outermost fraction of a disc.

        Raises for any other distribution: the formula is the disc's (ledger 18).
        """
        if self.distribution != "disc" or not self.edge_concentrates:
            raise ValueError(
                f"ratio_at_area_fraction is the disc's primary distribution; this "
                f"electrode's is {self.distribution!r}"
            )
        return disc_ratio_at_area_fraction(area_fraction)

    def describe(self) -> str:
        """Multi-line summary."""
        lines = [
            "Current density (leading phase)",
            f"  average       {self.average_A_per_cm2:.4g} A/cm^2 "
            f"({self.current_uA:g} uA over {self.area_cm2:.4g} cm^2)",
        ]
        if self.has_return_phase:
            lines.append(
                f"  return phase  {self.return_A_per_cm2:.4g} A/cm^2 "
                f"({self.return_phase_current_uA:g} uA x "
                f"{self.return_phase_width_us:g} us)"
            )
        lines += [
            f"  for scale     {self.relative_to_dbs_clinical:.2f}x the "
            f"{DBS_CLINICAL_REFERENCE_A_PER_CM2:g} A/cm^2 modelled for a clinical DBS "
            f"contact at 3 V",
        ]
        if self.distribution == "uniform":
            lines.append(
                "  uniform primary distribution: J = I/A everywhere on a sphere or "
                "hemisphere; no edge"
            )
        elif not self.edge_concentrates:
            lines.append("  recessed geometry: edge concentration designed out")
        elif self.distribution == "edge":
            lines.append(
                "  current crowds at this geometry's edges, so the local peak exceeds the "
                "average; the disc's centre and area-fraction figures do not apply and no "
                "closed form is used here"
            )
        else:
            lines += [
                f"  centre        {self.centre_ratio:.2f}x average "
                f"(primary distribution)",
                f"  outer {(self.fraction_above_average or 0.0) * 100:.0f} % of the surface "
                f"runs above average; density diverges at the rim",
            ]
        if self.threshold is not None:
            lines.append("  vs electroporation damage threshold:")
            lines.append(self.threshold.describe())
        if self.return_threshold is not None:
            lines.append(
                f"  return phase vs the threshold at its own "
                f"{self.return_phase_width_us:g} us width:"
            )
            lines.append(self.return_threshold.describe())
            lines.append(f"  binding phase: {self.binding_phase}")
        return "\n".join(lines)


def evaluate(
    current_uA: float,
    area_cm2: float,
    pulse_width_us: float,
    *,
    recessed: bool = False,
    diameter_um: float | None = None,
    n_pulses: int = butterwick2007.PULSE_COUNT_SATURATION,
    return_phase_current_uA: float = 0.0,
    return_phase_width_us: float = 0.0,
    electrode: Electrode | None = None,
) -> CurrentDensityResult:
    """Compute each phase's current density, the geometric peak factor, and the threshold.

    ``return_phase_current_uA`` and ``return_phase_width_us`` default to zero, which is
    "there is no second phase" and reproduces the pre-ledger-4 answer exactly. They are
    supplied by :mod:`neurostim.safety.assessment` from the protocol; passing one without
    the other is a return phase with no duration or no current, which is the same thing.

    ``electrode`` selects the primary distribution the result reports (ledger 18); it
    moves no number the threshold comparison uses. ``None`` reports the disc's, as before.
    """
    applied = average_current_density_A_per_cm2(current_uA, area_cm2)
    comparison = butterwick2007.compare(
        applied, pulse_width_us, diameter_um, n_pulses=n_pulses
    )
    return_applied = 0.0
    return_comparison = None
    if return_phase_current_uA > 0.0 and return_phase_width_us > 0.0:
        return_applied = average_current_density_A_per_cm2(
            return_phase_current_uA, area_cm2
        )
        return_comparison = butterwick2007.compare(
            return_applied, return_phase_width_us, diameter_um, n_pulses=n_pulses
        )
    distribution = primary_distribution(electrode)
    if recessed:
        fraction: float | None = 0.0
        centre: float | None = 1.0
    elif distribution == "disc":
        fraction, centre = DISC_FRACTION_ABOVE_AVERAGE, DISC_CENTRE_RATIO
    elif distribution == "uniform":
        fraction, centre = 0.0, 1.0
    else:
        fraction, centre = None, None
    return CurrentDensityResult(
        threshold=comparison,
        current_uA=current_uA,
        area_cm2=area_cm2,
        average_A_per_cm2=applied,
        pulse_width_us=pulse_width_us,
        edge_concentrates=not recessed and distribution != "uniform",
        fraction_above_average=fraction,
        centre_ratio=centre,
        return_phase_current_uA=return_phase_current_uA,
        return_phase_width_us=return_phase_width_us,
        return_A_per_cm2=return_applied,
        return_threshold=return_comparison,
        distribution=distribution,
    )
