"""Unit conversion helpers and canonical internal units.

Canonical internal units used throughout the package
----------------------------------------------------
============================  ==========================
Quantity                      Unit
============================  ==========================
current                       microampere (uA)
charge                        microcoulomb (uC)
charge density                microcoulomb / cm^2
time / pulse width            microsecond (us)
frequency                     hertz (Hz)
length                        micrometre (um)
area                          cm^2
voltage                       volt (V)
electrical conductivity       siemens / metre (S/m)
resistance                    ohm
temperature                   kelvin (absolute) / kelvin (differences)
power density                 watt / m^3
============================  ==========================

Public API is deliberately explicit -- ``uA_to_mA(x)`` rather than a units library --
so that a reader can audit every conversion in a report without installing anything.
"""

from __future__ import annotations

import math

# --- scale factors (multiply to convert FROM key TO the canonical unit) -----------

CHARGE_TO_UC: dict[str, float] = {
    "C": 1e6,
    "mC": 1e3,
    "uC": 1.0,
    "nC": 1e-3,
    "pC": 1e-6,
}

CURRENT_TO_UA: dict[str, float] = {
    "A": 1e6,
    "mA": 1e3,
    "uA": 1.0,
    "nA": 1e-3,
}

TIME_TO_US: dict[str, float] = {
    "s": 1e6,
    "ms": 1e3,
    "us": 1.0,
    "ns": 1e-3,
}

LENGTH_TO_UM: dict[str, float] = {
    "m": 1e6,
    "cm": 1e4,
    "mm": 1e3,
    "um": 1.0,
    "nm": 1e-3,
}

AREA_TO_CM2: dict[str, float] = {
    "m2": 1e4,
    "cm2": 1.0,
    "mm2": 1e-2,
    "um2": 1e-8,
    "nm2": 1e-14,
}

CHARGE_DENSITY_TO_UC_CM2: dict[str, float] = {
    "C/cm2": 1e6,
    "mC/cm2": 1e3,
    "uC/cm2": 1.0,
    "nC/cm2": 1e-3,
    "uC/mm2": 100.0,  # 1 mm^2 = 0.01 cm^2
    "mC/mm2": 1e5,
}


def _convert(value: float, unit: str, table: dict[str, float], kind: str) -> float:
    _check_finite(kind, value)
    try:
        return value * table[unit]
    except KeyError:
        raise ValueError(
            f"Unknown {kind} unit {unit!r}. Supported: {sorted(table)}"
        ) from None


def to_uC(value: float, unit: str) -> float:
    """Convert a charge to microcoulombs."""
    return _convert(value, unit, CHARGE_TO_UC, "charge")


def to_uA(value: float, unit: str) -> float:
    """Convert a current to microamperes."""
    return _convert(value, unit, CURRENT_TO_UA, "current")


def to_us(value: float, unit: str) -> float:
    """Convert a time to microseconds."""
    return _convert(value, unit, TIME_TO_US, "time")


def to_um(value: float, unit: str) -> float:
    """Convert a length to micrometres."""
    return _convert(value, unit, LENGTH_TO_UM, "length")


def to_cm2(value: float, unit: str) -> float:
    """Convert an area to square centimetres."""
    return _convert(value, unit, AREA_TO_CM2, "area")


def to_uC_cm2(value: float, unit: str) -> float:
    """Convert a charge density to microcoulombs per square centimetre."""
    return _convert(value, unit, CHARGE_DENSITY_TO_UC_CM2, "charge density")


# --- convenience round-trips used repeatedly in the safety maths -------------------

def um2_to_cm2(area_um2: float) -> float:
    """Square micrometres to square centimetres."""
    return area_um2 * 1e-8


def cm2_to_m2(area_cm2: float) -> float:
    """Square centimetres to square metres."""
    return area_cm2 * 1e-4


def um_to_m(length_um: float) -> float:
    """Micrometres to metres."""
    return length_um * 1e-6


def mC_cm2_to_uC_cm2(value: float) -> float:
    """Millicoulombs per cm^2 to microcoulombs per cm^2."""
    return value * 1e3


def uC_cm2_to_mC_cm2(value: float) -> float:
    """Microcoulombs per cm^2 to millicoulombs per cm^2."""
    return value * 1e-3


def charge_uC(current_uA: float, pulse_width_us: float) -> float:
    """Charge per phase for a rectangular constant-current pulse.

    ``Q[uC] = I[uA] * W[us] * 1e-6`` because uA*us = picocoulomb*1e6... explicitly:
    1 uA * 1 us = 1e-6 A * 1e-6 s = 1e-12 C = 1e-6 uC.
    """
    _check_finite("current_uA", current_uA)
    _check_finite("pulse_width_us", pulse_width_us)
    # charge_uC(100, -200) returned -0.02 uC (ledger 27). Zero is allowed: a phase of
    # no width carries no charge, as a monophasic pulse's return phase does.
    if pulse_width_us < 0:
        raise ValueError(f"pulse_width_us must be >= 0, got {pulse_width_us!r}")
    return current_uA * pulse_width_us * 1e-6


def current_uA_from_charge(charge_uC_value: float, pulse_width_us: float) -> float:
    """Invert :func:`charge_uC`: the constant current delivering a charge in a window."""
    _check_finite("charge_uC_value", charge_uC_value)
    _check_finite("pulse_width_us", pulse_width_us)
    if pulse_width_us <= 0:
        raise ValueError(f"pulse_width_us must be > 0, got {pulse_width_us!r}")
    return charge_uC_value / (pulse_width_us * 1e-6)


def _check_finite(name: str, value: float) -> None:
    """NaN and infinity were passed through every converter (ledger 27)."""
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")


# --- physical constants -----------------------------------------------------------

KELVIN_OFFSET = 273.15
"""Add to degrees Celsius to obtain kelvin."""


def celsius_to_kelvin(t_c: float) -> float:
    """Degrees Celsius to kelvin; below absolute zero raises (-300 C gave -26.85 K)."""
    _check_finite("t_c", t_c)
    if t_c < -KELVIN_OFFSET:
        raise ValueError(f"{t_c!r} C is below absolute zero")
    return t_c + KELVIN_OFFSET


def kelvin_to_celsius(t_k: float) -> float:
    """Kelvin to degrees Celsius; a negative kelvin temperature is below absolute zero."""
    _check_finite("t_k", t_k)
    if t_k < 0:
        raise ValueError(f"{t_k!r} K is below absolute zero")
    return t_k - KELVIN_OFFSET
