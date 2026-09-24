"""McCreery, Pikov & Troyk (2010) chronic microelectrode damage, and duty cycle.

*Neuronal loss due to prolonged controlled-current stimulation with chronically
implanted microelectrodes in the cat cerebral cortex*, J Neural Eng 7:036005.

This is the primary source behind the 4 nC/phase microelectrode threshold that
:mod:`neurostim.data.cogan2016` carries second-hand, and it is more informative than the
single number suggests.

The experiment
--------------
Activated iridium microelectrodes implanted **450 to 1282 days** in the sensorimotor
cortex of 7 adult cats, then pulsed for **240 h** (8 h/day for 30 days) at 50 Hz.

The result
----------
==========================  ==============  ============  ==========================
Charge per phase            Charge density  Duty cycle    Outcome
==========================  ==============  ============  ==========================
2 nC/phase                  100 uC/cm^2     continuous    no detectable change in
                                                          neuronal density
4 nC/phase                  200 uC/cm^2     100 %         neuron loss to a radius of
                                                          at least 150 um
4 nC/phase                  200 uC/cm^2     50 %          neuron loss to about 60 um
==========================  ==============  ============  ==========================

Two things follow that the single "4 nC/phase" figure hides.

**The threshold is bracketed, not located.** 2 nC/phase was safe and 4 nC/phase was
damaging under otherwise identical conditions. Quoting 4 nC/phase as *the* threshold
quotes the lowest level at which damage was actually seen, not the highest safe one.
:data:`NO_DAMAGE_NC_PER_PHASE` and :data:`DAMAGE_NC_PER_PHASE` keep both.

**Duty cycle matters, measurably.** Halving it -- one second on, one second off -- shrank
the damage radius from at least 150 um to about 60 um at identical charge per phase and
charge density. Neither the Shannon criterion nor the charge-per-phase threshold contains
duty cycle, and this is the clearest quantification of what that omission costs.

A caution the authors raise
---------------------------
There was also significant neuronal loss around the **unpulsed** control electrodes,
attributed to the implant itself. Chronic microelectrode damage is not solely a
stimulation effect, and a stimulation-safety calculation does not bound it.
"""

from __future__ import annotations

NO_DAMAGE_NC_PER_PHASE = 2.0
"""Highest charge per phase producing no detectable change (100 uC/cm^2, continuous)."""

DAMAGE_NC_PER_PHASE = 4.0
"""Lowest charge per phase at which neuron loss was observed.

This is the figure usually quoted as "the 4 nC/phase threshold". It is the damaging
level, not the safe one.
"""

NO_DAMAGE_CHARGE_DENSITY_UC_CM2 = 100.0
DAMAGE_CHARGE_DENSITY_UC_CM2 = 200.0

DAMAGE_RADIUS_CONTINUOUS_UM = 150.0
"""Neuron loss extended at least this far at 100 % duty cycle."""

DAMAGE_RADIUS_HALF_DUTY_UM = 60.0
"""At 50 % duty cycle, the radius of the loss the stimulation itself induced.

Not the whole loss: the insertion injury "was responsible for most of the neuronal loss
within 150 um of the electrodes pulsed with the 50% duty cycle" (p. 1; S-12)."""

DUTY_CYCLE_RADIUS_RATIO = DAMAGE_RADIUS_CONTINUOUS_UM / DAMAGE_RADIUS_HALF_DUTY_UM
"""Halving duty cycle shrank the damage radius by at least this factor."""

IMPLANT_DURATION_DAYS = (450, 1282)
PULSING_HOURS = 240.0
FREQUENCY_HZ = 50.0
N_ANIMALS = 7
PREPARATION = "activated iridium microelectrodes, cat sensorimotor cortex"
UNPULSED_CONTROLS_ALSO_DAMAGED = True
"""Control electrodes showed loss too, attributed to the implant rather than pulsing."""

REFERENCE = "mccreery2010"

# --- the conditions that make 4 nC/phase mean anything (ledger 77, S-12) ----------------
# Quoted from the author manuscript (PMC), pages as numbered there.

PULSE_WIDTH_US = 200.0
INTERPULSE_BIAS_V = 0.6
"""Anodic bias of the activated iridium, applied "in order to increase their charge
capacity" -- so the 4 nC/phase is not a charge an unbiased electrode could carry."""
ELECTRODE_AREA_UM2 = (2000.0, 150.0)
"""Geometric area, mean and spread: "2,000 +/- 150 um2" (p. 2)."""
POLARITY = "cathodic"

CONDITIONS_QUOTE = (
    "Each electrode was pulsed at 50 pps with cathodic pulses 200 μs in duration and "
    "10 or 20 μA in amplitude (2 or 4 nC/phase). The activated iridium "
    "microelectrodes were biased to + 0.6 volts with respect to the platinum "
    "indifferent electrode, in order to increase their charge capacity."
)
"""Author manuscript p. 3."""

INSERTION_LOSS_QUOTE = (
    "this was responsible for most of the neuronal loss within 150 μm of the "
    "electrodes pulsed with the 50% duty cycle."
)
"""Author manuscript p. 1 (abstract): the implant's own injury, not the stimulation,
accounts for most of the loss within 150 um at 50 % duty."""

_CONDITIONS = (
    "cathodic 200 us pulses at 50 Hz, +0.6 V interpulse bias, 2000 um^2 activated "
    "iridium"
)


def duty_cycle_note(duty_cycle: float) -> str:
    """A sourced statement about duty cycle, without inventing a scaling law.

    Only two duty cycles were tested, so this reports the measured contrast rather than
    interpolating between them.
    """
    if duty_cycle >= 0.95:
        return (
            f"Duty cycle {duty_cycle * 100:.0f} %: at 100 % duty McCreery et al. (2010) "
            f"found neuron loss to a radius of at least "
            f"{DAMAGE_RADIUS_CONTINUOUS_UM:g} um at 4 nC/phase ({_CONDITIONS}), against "
            f"stimulation-induced loss within about {DAMAGE_RADIUS_HALF_DUTY_UM:g} um "
            f"for the same stimulus at 50 % duty."
        )
    if duty_cycle <= 0.55:
        return (
            f"Duty cycle {duty_cycle * 100:.0f} %: at 50 % duty the stimulation-induced "
            f"loss reached about {DAMAGE_RADIUS_HALF_DUTY_UM:g} um, against at least "
            f"{DAMAGE_RADIUS_CONTINUOUS_UM:g} um continuously, at identical charge per "
            f"phase ({_CONDITIONS}); the insertion injury accounted for most of the "
            f"loss within 150 um at 50 % duty."
        )
    return (
        f"Duty cycle {duty_cycle * 100:.0f} %: only 50 % and 100 % were tested "
        f"(stimulation-induced loss within about {DAMAGE_RADIUS_HALF_DUTY_UM:g} um and "
        f"loss to at least {DAMAGE_RADIUS_CONTINUOUS_UM:g} um respectively, "
        f"{_CONDITIONS}); intermediate values were not measured and are not "
        f"interpolated here."
    )
