"""The stimulator voltage over one biphasic pulse, followed step by step (ledger 135).

The package's compliance budget is a closed form per phase. This oracle integrates the same
circuit -- a series resistance ``R`` and one capacitive interface per electrode -- through
the leading phase and the return phase, and reports the largest stimulator voltage reached.
It evaluates no closed form.

Each interface is a capacitor whose areal capacitance depends on the sign of the charge it
holds, one value per polarity branch. That is the package's polarity-specific ``C_eff``:
``C_cathodic`` while the stored charge is cathodic (negative), ``C_anodic`` while it is
anodic. The active electrode holds charge ``q`` and the counter ``-q``. The voltage the
stimulator must supply is ``|I R + phi_a(q) - phi_c(-q)|``.

What this makes visible, and what the old return-phase term got wrong: a return phase that
does not overshoot rest only *discharges* the leading phase's branch. The interface voltage
then opposes the drive, and the stimulator never needs more than ``I_ret R``. The opposite
branch is reached only by an overshoot, ``(r_a - 1) Q``, and only that part polarises at the
opposite polarity.

Nothing here imports ``neurostim``.
"""

from __future__ import annotations


def peak_stimulator_voltage_V(
    *,
    current_uA: float,
    pulse_width_us: float,
    return_phase_ratio: float,
    recovered_fraction: float,
    anodic_first: bool,
    resistance_ohm: float,
    area_cm2: float,
    c_cathodic_uF_cm2: float,
    c_anodic_uF_cm2: float,
    counter_area_cm2: float | None = None,
    counter_c_cathodic_uF_cm2: float | None = None,
    counter_c_anodic_uF_cm2: float | None = None,
    steps: int = 20_000,
) -> float:
    """Largest ``|V|`` the stimulator supplies over the leading and the return phase."""

    def phi(q_uC: float, area: float, c_cath: float, c_anod: float) -> float:
        capacitance = c_cath if q_uC < 0.0 else c_anod
        return (q_uC / area) / capacitance  # uC/cm^2 over uF/cm^2 is volts

    def voltage(i_uA: float, q_uC: float) -> float:
        v = i_uA * 1e-6 * resistance_ohm + phi(q_uC, area_cm2, c_cathodic_uF_cm2, c_anodic_uF_cm2)
        if counter_area_cm2 is not None:
            assert counter_c_cathodic_uF_cm2 is not None and counter_c_anodic_uF_cm2 is not None
            v -= phi(-q_uC, counter_area_cm2, counter_c_cathodic_uF_cm2, counter_c_anodic_uF_cm2)
        return abs(v)

    sign = 1.0 if anodic_first else -1.0
    i_lead = sign * current_uA
    i_ret = -sign * current_uA * recovered_fraction / return_phase_ratio
    w_ret = pulse_width_us * return_phase_ratio
    peak = 0.0
    q = 0.0
    for i_uA, width in ((i_lead, pulse_width_us), (i_ret, w_ret)):
        dq = i_uA * 1e-6 * (width / steps)  # uC per step
        for _ in range(steps):
            q += dq
            peak = max(peak, voltage(i_uA, q))
    return peak
