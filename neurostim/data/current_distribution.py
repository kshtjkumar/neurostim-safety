"""Non-uniform current distribution, and what it does to a charge-density limit.

Every charge density in this package is a **geometric average**: charge per phase
divided by geometric surface area. Real electrodes do not deliver current uniformly.
The primary current distribution on a non-recessed disc diverges at the perimeter
(Rubinstein et al. 1987), so part of the surface always operates above the average.

The quantitative statement
--------------------------
Kuncel & Grill (2004) modelled a clinical DBS contact -- 1.26 mm diameter, 1.5 mm long,
driven at 3 V -- and found an average current density of 0.0993 A/cm^2 with
**25.6 % of the contact surface operating above that average**.

Why it matters for the limits used here
---------------------------------------
The 30 uC/cm^2 DBS limit, and the Shannon fit behind it, were both derived from
surface-*averaged* charge densities. Applying them to an averaged value is therefore
self-consistent; the caveat is that the local peak is higher than the number being
compared, so the margin against local damage is smaller than the reported margin.
Kuncel & Grill list this as one of three reasons the 30 uC/cm^2 limit is a **liberal**
estimate rather than a conservative one.

Their other two reasons:

1. the data behind the limit were collected at frequencies far below DBS rates, and a
   frequency-dependent damage threshold has been reported (Agnew et al. 1983);
2. the reassuring human post-mortem studies used charge densities well below the limit,
   so they confirm only that low-charge stimulation is non-damaging -- they do not
   validate the limit itself.

Mitigations reported in the literature
--------------------------------------
Three, in increasing order of how easily they can be retrofitted:

**Geometry.** Recessing the electrode into its carrier, or flaring the recess opening,
reduces or eliminates the edge concentration. Rubinstein et al. (1987) solved the
recessed disc by a Green's function approach and found a more uniform profile both at
the electrode surface and at the carrier-tissue junction.

**Surface film.** McIntyre & Grill (2001) found current density concentrates at a
microelectrode tip, and that a thin, modestly conducting coating makes the distribution
markedly more uniform -- the voltage drop across the film acts like a reaction
overpotential.

**Waveform.** Wang et al. (2014) showed that shaping the leading edge of the current
pulse lowers the peak edge current density, which is the only one of the three available
after an electrode is already built.

Reaction kinetics also help on their own: as a pulse proceeds, activation overpotentials
push the distribution from the sharply non-uniform *primary* form toward a more uniform
*secondary* form, more so at longer pulse widths and higher current densities
(Cogan et al. 2016). An ideally non-polarisable electrode -- or a saline-filled pipette,
which has no interface at all -- keeps the primary distribution throughout and is
correspondingly worse.
"""

from __future__ import annotations

DBS_FRACTION_ABOVE_AVERAGE = 0.256
"""Fraction of a clinical DBS contact operating above its average current density.

Kuncel & Grill (2004), 1.26 mm x 1.5 mm contact at 3 V.
"""

DBS_AVERAGE_CURRENT_DENSITY_A_PER_CM2 = 0.0993
"""Average current density in that model case."""

DBS_MODELLED_CONTACT_DIAMETER_MM = 1.26
DBS_MODELLED_CONTACT_LENGTH_MM = 1.5
DBS_MODELLED_VOLTAGE_V = 3.0

PT_EDGE_CORROSION_OBSERVED_UC_CM2 = 240.0
"""Preferential corrosion at platinum disc edges, reported at this average density.

Wang & Weiland (2012), via Cogan et al. (2016). Direct evidence that the edge
concentration is real and consequential, not merely a modelling artefact.
"""

REFERENCE = "kuncel_grill2004_full"


def peak_is_above_average() -> bool:
    """Whether any part of a non-recessed electrode exceeds the average density.

    Always true for a non-recessed disc or band. Present as a named function so the
    assumption is explicit at call sites rather than implied.
    """
    return True


def averaged_density_understates_local_peak(recessed: bool = False) -> bool:
    """Whether the geometric-average charge density understates the local maximum.

    Returns ``False`` for a recessed electrode, where the edge concentration is
    designed out.
    """
    return not recessed
