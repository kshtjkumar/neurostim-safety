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
"""At 50 % duty cycle the same stimulus damaged only about this radius."""

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


def duty_cycle_note(duty_cycle: float) -> str:
    """A sourced statement about duty cycle, without inventing a scaling law.

    Only two duty cycles were tested, so this reports the measured contrast rather than
    interpolating between them.
    """
    if duty_cycle >= 0.95:
        return (
            f"Duty cycle {duty_cycle * 100:.0f} %: at 100 % duty McCreery et al. (2010) "
            f"found neuron loss to a radius of at least "
            f"{DAMAGE_RADIUS_CONTINUOUS_UM:g} um at 4 nC/phase, against about "
            f"{DAMAGE_RADIUS_HALF_DUTY_UM:g} um for the same stimulus at 50 % duty."
        )
    if duty_cycle <= 0.55:
        return (
            f"Duty cycle {duty_cycle * 100:.0f} %: reducing duty cycle to 50 % shrank "
            f"the damage radius from at least {DAMAGE_RADIUS_CONTINUOUS_UM:g} um to "
            f"about {DAMAGE_RADIUS_HALF_DUTY_UM:g} um at identical charge per phase."
        )
    return (
        f"Duty cycle {duty_cycle * 100:.0f} %: only 50 % and 100 % were tested "
        f"(damage radius about {DAMAGE_RADIUS_HALF_DUTY_UM:g} um and at least "
        f"{DAMAGE_RADIUS_CONTINUOUS_UM:g} um respectively); intermediate values were "
        f"not measured and are not interpolated here."
    )
