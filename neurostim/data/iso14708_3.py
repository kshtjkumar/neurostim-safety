"""ISO 14708-3:2017 clause 17.1 -- the regulatory heat criterion for neurostimulators.

Until this was read, the thermal limit in this package was 1 K, a convention adopted for
reporting with no standard behind it. This module replaces it with the actual
requirement.

The requirement
---------------
An implantable part of an implantable neurostimulator (INS), not intended to supply
heat, shall satisfy **at least one** of:

a. no outer surface greater than **39 degrees C**;
b. no tissue receiving a thermal dose greater than the CEM43 thresholds in Table 101;
c. manufacturer's evidence that a higher rise is justified for the application.

Because option (a) is the simplest to demonstrate, and because Formula (1) is only
declared valid from 39 C upward, the practical design target for a 37 C baseline is a
**2 K** rise. That also matches the standard's own MRI acceptance criterion, where a
temperature rise of 2 C or less needs no further scientific rationale.

CEM43
-----
Cumulative Equivalent Minutes at 43 C converts a time-temperature history into a single
dose:

.. math::

    \\mathrm{CEM43} = \\sum_{i=1}^{n} t_i \\, R^{(43 - T_i)}

with ``t_i`` in minutes, ``T_i`` the mean tissue temperature in degrees C over that
interval, and ``R = 0.25`` below 43 C, ``0.5`` at or above it. The standard states the
formula is valid between 39 C and 57 C.

Brain is the limiting tissue
----------------------------
Table 101 gives brain a threshold of **2**, against 40 for muscle, fat and peripheral
nerve -- a twentyfold difference. Anything implanted in the brain is held to a far
stricter thermal dose than the same device in muscle or nerve.

Scope note
----------
These thresholds govern the *device*, in normal operation including recharge. They are
not a tissue-damage criterion for the stimulation current itself, which is what the
Shannon and charge-injection checks address. A protocol can satisfy ISO 14708-3 on heat
and still injure tissue electrically, and vice versa.
"""

from __future__ import annotations

import math

BASELINE_BODY_TEMPERATURE_C = 37.0
"""Assumed baseline for converting an absolute limit into a permitted rise."""

MAX_OUTER_SURFACE_C = 39.0
"""Clause 17.1(a): no outer surface of the implant above this temperature."""

MAX_RISE_K = MAX_OUTER_SURFACE_C - BASELINE_BODY_TEMPERATURE_C
"""The 2 K design target implied by clause 17.1(a) at a 37 C baseline."""

MRI_NO_RATIONALE_RISE_C = 2.0
"""Table 102: an MRI-induced rise at or below 2 C needs no further rationale."""

CEM43_VALID_RANGE_C = (39.0, 57.0)
"""Temperature range over which the standard declares Formula (1) valid."""

CEM43_THRESHOLDS: dict[str, float] = {
    "muscle": 40.0,
    "fat": 40.0,
    "peripheral nerve": 40.0,
    "skin": 21.0,
    "bone": 16.0,
    "brain": 2.0,
    "blood brain barrier": 15.0,
}
"""Table 101, verbatim. Brain is the most restrictive tissue by a factor of twenty."""

R_BELOW_43 = 0.25
"""``R`` in Formula (1) for temperatures below 43 C."""

R_AT_OR_ABOVE_43 = 0.5
"""``R`` in Formula (1) for temperatures at or above 43 C."""

REFERENCE = "iso14708_3_2017"


def cem43(temperatures_C: list[float], minutes: list[float]) -> float:
    """Cumulative Equivalent Minutes at 43 C for a time-temperature history.

    Parameters
    ----------
    temperatures_C:
        Mean tissue temperature over each interval.
    minutes:
        Duration of each interval, in minutes.

    Intervals below the 39 C lower bound of the standard's validity range contribute
    nothing, matching the fact that clause 17.1(a) treats staying under 39 C as
    sufficient on its own. Including them would accumulate a spurious dose from normal
    body temperature.
    """
    if len(temperatures_C) != len(minutes):
        raise ValueError(
            f"temperatures_C and minutes must be the same length, got "
            f"{len(temperatures_C)} and {len(minutes)}"
        )
    total = 0.0
    for temperature, duration in zip(temperatures_C, minutes, strict=True):
        if duration < 0:
            raise ValueError(f"interval durations must be >= 0, got {duration!r}")
        if not math.isfinite(temperature):
            raise ValueError(f"temperatures must be finite, got {temperature!r}")
        if temperature < CEM43_VALID_RANGE_C[0]:
            continue
        r = R_AT_OR_ABOVE_43 if temperature >= 43.0 else R_BELOW_43
        total += duration * r ** (43.0 - temperature)
    return total


def cem43_steady(temperature_C: float, minutes: float) -> float:
    """CEM43 for a single sustained temperature."""
    return cem43([temperature_C], [minutes])


def allowed_minutes(temperature_C: float, tissue: str = "brain") -> float:
    """How long a tissue may sit at a temperature before reaching its CEM43 threshold.

    Returns ``inf`` below 39 C, where the standard's formula does not apply and clause
    17.1(a) is satisfied outright.
    """
    threshold = threshold_for(tissue)
    if temperature_C < CEM43_VALID_RANGE_C[0]:
        return math.inf
    r = R_AT_OR_ABOVE_43 if temperature_C >= 43.0 else R_BELOW_43
    per_minute = r ** (43.0 - temperature_C)
    return threshold / per_minute


def threshold_for(tissue: str = "brain") -> float:
    """CEM43 threshold for a named tissue from Table 101."""
    key = tissue.strip().lower()
    try:
        return CEM43_THRESHOLDS[key]
    except KeyError:
        raise KeyError(
            f"No CEM43 threshold for {tissue!r}. Table 101 covers: "
            f"{sorted(CEM43_THRESHOLDS)}"
        ) from None


def rise_is_acceptable(rise_K: float) -> bool:
    """Whether a steady rise satisfies clause 17.1(a) at a 37 C baseline."""
    return rise_K <= MAX_RISE_K
