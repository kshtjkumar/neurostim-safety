"""McCreery et al. (1995) frequency dependence of stimulation-induced nerve damage.

*Relationship between stimulus amplitude, stimulus frequency and neural damage during
electrical stimulation of sciatic nerve of cat*, Med Biol Eng Comput 33:426-9.

This is the source behind the statement, repeated in every later review, that frequency
matters and that the Shannon criterion does not contain it.

The experiment
--------------
Cat sciatic nerve, chronically implanted helical platinum band electrodes encircling the
nerve. **8 h of continuous stimulation**, charge-balanced biphasic, 100 us per phase with
a 400 us interphase delay. Damage scored as early axonal degeneration (EAD) in a full
cross-section, **seven days after** the stimulation, normalised to 22 000 myelinated
axons.

The result
----------
============  ==========================  =============================  =====
Frequency     Damage slope (% EAD per      Threshold (multiples of full   R
              alpha unit)                  alpha recruitment)
============  ==========================  =============================  =====
20 Hz         0.003                        none resolvable                0.07
50 Hz         0.37                         1.1                            0.87
100 Hz        1.1                          0.8                            0.85
============  ==========================  =============================  =====

Doubling the rate from 50 to 100 Hz **tripled the damage slope** and lowered the damage
threshold to about **0.73x**. At 20 Hz there was no correlation between amplitude and
damage at all: in the authors' words, continuous low-frequency stimulation "induces
little or no neural injury, even when the stimulus amplitude is very high".

Their conclusion is a design rule: "the margin of safety ... can be greatly increased by
reducing the stimulus frequency to the absolute minimum required to obtain the desired
clinical results."

Why this cannot become a charge-density derating
------------------------------------------------
Read this before trying to fold these numbers into a charge limit. The authors normalise
stimulus amplitude to the current that **fully recruits the alpha component** of the
evoked compound action potential, and state that "the correlation between neural damage
and stimulus amplitude is poor when the stimulus is expressed simply as charge per phase
or as current."

So the damage axis here is *physiological recruitment*, not charge. There is no valid
conversion from these thresholds to a multiplier on a charge-density limit, and this
module therefore exposes the measured relationship without pretending otherwise. What it
supports is a quantified warning, not a derated number.

Two further limits the authors state
------------------------------------
- ``R^2`` is 0.75 at 50 Hz and 0.72 at 100 Hz, so a quarter of the variance between
  nerves is not explained by amplitude and frequency together.
- They doubt quantitative extrapolation "between species, across patients' age groups,
  or to the very long periods of stimulation that are required for a clinically useful
  FES system".

And the preparation is **peripheral nerve**, not cortex.
"""

from __future__ import annotations

from dataclasses import dataclass

PULSE_WIDTH_US = 100.0
INTERPHASE_GAP_US = 400.0
DURATION_H = 8.0
ASSESSMENT_DELAY_DAYS = 7
PREPARATION = "cat sciatic nerve, helical platinum band electrodes"
DAMAGE_MEASURE = "early axonal degeneration (EAD), % of myelinated axons"
AMPLITUDE_UNITS = "multiples of the current for full alpha-component recruitment"


@dataclass(frozen=True)
class FrequencyPoint:
    """One stimulation frequency and its fitted damage relationship."""

    frequency_hz: float
    slope_percent_ead_per_alpha_unit: float
    threshold_alpha_units: float | None
    correlation_r: float
    n_nerves: int
    note: str = ""

    @property
    def amplitude_correlates(self) -> bool:
        """Whether damage correlated with amplitude at this frequency."""
        return self.correlation_r > 0.5


TABLE: tuple[FrequencyPoint, ...] = (
    FrequencyPoint(
        frequency_hz=20.0,
        slope_percent_ead_per_alpha_unit=0.003,
        threshold_alpha_units=None,
        correlation_r=0.07,
        n_nerves=8,
        note=(
            "No distinct damage threshold and no correlation with amplitude. A small "
            "amount of EAD appeared in three nerves above twice full recruitment, which "
            "the authors suggest may be a vulnerable subpopulation (<0.2 % of axons) or "
            "incidental mechanical injury."
        ),
    ),
    FrequencyPoint(
        frequency_hz=50.0,
        slope_percent_ead_per_alpha_unit=0.37,
        threshold_alpha_units=1.1,
        correlation_r=0.87,
        n_nerves=15,
        note="Reference group, previously reported in McCreery et al. (1992).",
    ),
    FrequencyPoint(
        frequency_hz=100.0,
        slope_percent_ead_per_alpha_unit=1.1,
        threshold_alpha_units=0.8,
        correlation_r=0.85,
        n_nerves=9,
    ),
)

SLOPE_RATIO_50_TO_100 = 1.1 / 0.37
"""Damage accumulates about three times faster per unit amplitude at 100 Hz than 50 Hz."""

THRESHOLD_RATIO_50_TO_100 = 0.8 / 1.1
"""Damage threshold at 100 Hz is about 0.73x its value at 50 Hz."""

LOW_FREQUENCY_SAFE_HZ = 20.0
"""At and below this rate the authors found no amplitude-dependent damage."""

R_SQUARED_UNEXPLAINED = 0.25
"""Roughly a quarter of between-nerve variance is unexplained by amplitude and rate."""

REFERENCE = "mccreery1995"


def point_at(frequency_hz: float) -> FrequencyPoint | None:
    """The measured point at a frequency, if one exists. No interpolation."""
    for p in TABLE:
        if p.frequency_hz == frequency_hz:
            return p
    return None


def describe_frequency_risk(frequency_hz: float) -> str:
    """A sourced statement about frequency risk, without inventing a derating.

    Deliberately returns prose rather than a factor. The measured relationship is
    expressed in recruitment units on peripheral nerve, and there is no supported
    conversion to a charge-density multiplier.
    """
    if frequency_hz <= LOW_FREQUENCY_SAFE_HZ:
        return (
            f"At {frequency_hz:g} Hz: McCreery et al. (1995) found no correlation "
            f"between amplitude and axonal degeneration at 20 Hz (R = 0.07) even at "
            f"very high amplitudes, in cat sciatic nerve over 8 h."
        )
    if frequency_hz <= 50.0:
        return (
            f"At {frequency_hz:g} Hz: at 50 Hz the measured damage threshold was 1.1x "
            f"full alpha recruitment with a slope of 0.37 % EAD per unit "
            f"(cat sciatic nerve, 8 h)."
        )
    fold = frequency_hz / 50.0
    return (
        f"At {frequency_hz:g} Hz: {fold:.1f}x the 50 Hz reference. Between 50 and "
        f"100 Hz the damage slope tripled (0.37 -> 1.1 % EAD per unit) and the "
        f"threshold fell to 0.73x. The trend beyond 100 Hz was not measured, and the "
        f"relationship is in recruitment units on peripheral nerve, so no charge-based "
        f"derating follows from it."
    )
