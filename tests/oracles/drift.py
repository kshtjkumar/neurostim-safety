"""How long a net DC current takes to drive an electrode out of its water window.

A monophasic pulse train injects charge and never recovers it. The interface behaves as a
capacitor of areal capacitance ``C`` charged by the mean current, so the potential ramps
and eventually leaves the window. The package reports the monophasic case as a PASS with
0.58 V of headroom, because every limit it applies is a per-pulse limit measured on a
charge-balanced waveform. On the audit's case -- a clinical band, 3000 uA at 90 us and
130 Hz -- the interface actually leaves a 0.6 V window in about a quarter of a second.

Two independent routes to that number live here.

:func:`drift_time_s` adds one pulse's charge at a time and asks, after each, whether the
potential has left the window. It evaluates no formula for the answer: it is a loop over
pulses, so it is an oracle for the closed form rather than a restatement of it.

:func:`drift_time_s_closed_form` is the continuous limit, ``t = window * C / J_dc``. The
two agree to within the duration of one pulse by construction, which is the strongest
statement that can be made: a pulse train cannot resolve time more finely than its own
period.

Nothing here imports ``neurostim``. The capacitance, the window and the area are inputs,
because each has its own provenance and none of them is this oracle's business to derive.
"""

from __future__ import annotations

import math


def net_dc_current_uA(current_uA: float, pulse_width_us: float, frequency_hz: float) -> float:
    """Mean current of an unrecovered monophasic train: ``I * W * f``.

    Written as a duty cycle times the amplitude, in SI, so no factor can hide:
    ``W[us] * 1e-6`` is the pulse duration in seconds and ``f`` its repetition rate, so
    ``W * f`` is the dimensionless fraction of time current flows.
    """
    duty = (pulse_width_us * 1e-6) * frequency_hz
    return current_uA * duty


def drift_time_s(
    *,
    current_uA: float,
    pulse_width_us: float,
    frequency_hz: float,
    area_cm2: float,
    capacitance_uF_cm2: float,
    window_V: float,
    max_pulses: int = 100_000_000,
) -> float:
    """Time at which the interface first leaves the window, by pulse-by-pulse accumulation.

    Returns ``inf`` if the window is not reached within ``max_pulses``, never a truncated
    answer presented as a real one.
    """
    if frequency_hz <= 0.0:
        raise ValueError(f"frequency_hz must be > 0, got {frequency_hz!r}")
    if window_V <= 0.0:
        raise ValueError(f"window_V must be > 0, got {window_V!r}")

    charge_per_pulse_C = (current_uA * 1e-6) * (pulse_width_us * 1e-6)
    capacitance_F = (capacitance_uF_cm2 * 1e-6) * area_cm2
    if capacitance_F <= 0.0:
        raise ValueError("area_cm2 and capacitance_uF_cm2 must both be > 0")

    potential_V = 0.0
    for pulse in range(1, max_pulses + 1):
        potential_V += charge_per_pulse_C / capacitance_F
        if potential_V >= window_V:
            return pulse / frequency_hz
    return math.inf


def drift_time_s_closed_form(
    *,
    current_uA: float,
    pulse_width_us: float,
    frequency_hz: float,
    area_cm2: float,
    capacitance_uF_cm2: float,
    window_V: float,
) -> float:
    """``t = window * C / J_dc``, the continuous limit of :func:`drift_time_s`."""
    dc_A_per_cm2 = net_dc_current_uA(current_uA, pulse_width_us, frequency_hz) * 1e-6 / area_cm2
    volts_per_second = dc_A_per_cm2 / (capacitance_uF_cm2 * 1e-6)
    if volts_per_second <= 0.0:
        return math.inf
    return window_V / volts_per_second
