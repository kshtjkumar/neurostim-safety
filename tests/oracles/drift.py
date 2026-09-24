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


def partial_recovery_exit_time_s(
    *,
    current_uA: float,
    pulse_width_us: float,
    recovered_fraction: float,
    frequency_hz: float,
    area_cm2: float,
    capacitance_uF_cm2: float,
    leading_window_V: float,
    opposite_window_V: float,
    max_pulses: int = 10_000_000,
    opposite_capacitance_uF_cm2: float | None = None,
) -> float:
    """First time the interface leaves the window, following every phase of every pulse.

    The monophasic loop above cannot see what a return phase does, and that is where the
    closed form's error hid (ledger 105). Here each pulse is two steps on the same
    capacitor: the leading phase moves the potential ``e = Q / C`` toward the leading edge,
    and the peak is checked there. The return phase then moves it ``recovered_fraction *
    e`` back, and the potential is checked against the opposite edge. Whatever is left
    over is carried into the next pulse. No closed form is evaluated. Pulse ``n``
    (1-indexed) is reported at ``n / f``, the convention :func:`drift_time_s` uses.

    ``leading_window_V`` and ``opposite_window_V`` are the positive distances from rest to
    the edge in the leading phase's direction and to the other edge.

    ``opposite_capacitance_uF_cm2`` is the areal capacitance while the stored charge sits on
    the other side of rest (ledger 141). The loop then follows the *charge*, and turns it into
    a potential with whichever branch holds it: ``capacitance_uF_cm2`` on the leading side,
    this one on the other. Omitted, one capacitance serves both, and the loop is the one
    above, step for step.

    Returns ``inf`` if the window is not left within ``max_pulses``.
    """
    if frequency_hz <= 0.0:
        raise ValueError(f"frequency_hz must be > 0, got {frequency_hz!r}")
    charge_C = (current_uA * 1e-6) * (pulse_width_us * 1e-6)
    capacitance_F = (capacitance_uF_cm2 * 1e-6) * area_cm2
    excursion_V = charge_C / capacitance_F

    if opposite_capacitance_uF_cm2 is None:
        potential_V = 0.0  # signed: positive is toward the leading phase's edge
        for pulse in range(1, max_pulses + 1):
            potential_V += excursion_V
            if potential_V > leading_window_V:
                return pulse / frequency_hz
            potential_V -= recovered_fraction * excursion_V
            if -potential_V > opposite_window_V:
                return pulse / frequency_hz
        return math.inf

    opposite_F = (opposite_capacitance_uF_cm2 * 1e-6) * area_cm2

    def potential(q_C: float) -> float:
        return q_C / (capacitance_F if q_C >= 0.0 else opposite_F)

    stored_C = 0.0  # signed: positive is on the leading phase's side of rest
    for pulse in range(1, max_pulses + 1):
        stored_C += charge_C
        if potential(stored_C) > leading_window_V:
            return pulse / frequency_hz
        stored_C -= recovered_fraction * charge_C
        if -potential(stored_C) > opposite_window_V:
            return pulse / frequency_hz
    return math.inf


def exits_within_delivered_pulses(
    *,
    train_duration_s: float,
    train_duty_cycle: float,
    frequency_hz: float,
    **kwargs: float,
) -> bool:
    """Whether the interface leaves the window within the pulses the train delivers.

    Ledger 109. The capacitor has no leakage, so an off-period neither adds nor removes
    offset: only delivered pulses count. A train of ``T`` seconds at duty ``d`` delivers
    ``ceil(T f d)`` pulses (the count the compliance budget uses, rounded up so a partial
    burst counts). This steps exactly those pulses through
    :func:`partial_recovery_exit_time_s` and reports whether any of them leaves the window.
    A continuous train delivers every pulse.
    """
    import math as _math

    if _math.isinf(train_duration_s):
        pulses = 10_000_000
    else:
        pulses = _math.ceil(train_duration_s * frequency_hz * train_duty_cycle)
    exit_s = partial_recovery_exit_time_s(
        frequency_hz=frequency_hz, max_pulses=pulses, **kwargs  # type: ignore[arg-type]
    )
    return _math.isfinite(exit_s)
