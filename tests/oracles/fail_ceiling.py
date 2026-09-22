"""The highest amplitude at which no check FAILs, found by binary search.

This is the definition of "limiting current" the fix plan settles on, computed without
reading the package's answer. It consults exactly one thing: whether
``SafetyCalculator.assess().failed`` is empty. It never touches ``limiting_current_uA``,
``limiting_mechanism``, ``margin``, or any per-check maximum -- which is what makes it a
legitimate expected value for all of those.

Why this is needed. On the plan's worked example -- ``RingElectrode(330, 270, "Pt")`` at
80 uA, 200 us, 130 Hz -- the package reports a limiting current of 141.37 uA while two
checks are in a FAIL state at 80 uA. The true ceiling is 20.0 uA, so the headline is 7.07x
the highest amplitude at which nothing fails. A test written against the package's own
``min(...)`` expression cannot see that; this one can.

The search is over floats, not over a fixed tolerance: it narrows until the bracket is one
ulp wide, so it returns the exact boundary float rather than something near it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

# The searched amplitude is in microamps. One amp is far above any electrode this package
# describes, so a bracket that reaches it and still does not FAIL means there is no ceiling.
_DEFAULT_UPPER_uA = 1e6

# StimProtocol rejects a zero amplitude, so the bracket starts at a femtoamp instead. A
# protocol that already FAILs there has no usable amplitude at all, and the answer is 0.
_DEFAULT_LOWER_uA = 1e-12


def rebuild_at(calculator: Any, current_uA: float) -> Any:
    """The same calculator with only the amplitude changed.

    Every construction argument is carried across explicitly. A ``copy`` would be shorter
    and would silently inherit any future field; naming them means a new field that
    changes the verdict shows up here as a missing argument rather than as a wrong answer.
    """
    from neurostim import SafetyCalculator

    return SafetyCalculator(
        calculator.e,
        replace(calculator.p, current_uA=current_uA),
        calculator.k,
        material=calculator.material,
        policy=calculator.policy,
        medium=calculator.medium,
        tissue_conductivity_S_per_m=calculator.tissue_conductivity_S_per_m,
        lead_resistance_ohm=calculator.lead_resistance_ohm,
        compliance_V=calculator.compliance_V,
        measured_impedance_ohm=calculator.measured_impedance_ohm,
        resting_potential_V=calculator.resting_potential_V,
        capacitance_uF_cm2=calculator.capacitance_uF_cm2,
    )


def no_check_fails(calculator: Any, current_uA: float) -> bool:
    """Whether the assessment at ``current_uA`` has an empty ``failed`` tuple.

    The only property of the package this oracle reads.
    """
    return not rebuild_at(calculator, current_uA).assess().failed


def fail_ceiling_uA(
    calculator: Any,
    *,
    lower_uA: float = _DEFAULT_LOWER_uA,
    upper_uA: float = _DEFAULT_UPPER_uA,
) -> float:
    """Largest amplitude at which ``assess().failed`` is empty.

    Returns ``0.0`` when even an infinitesimal amplitude FAILs, and ``inf`` when nothing
    fails anywhere up to ``upper_uA`` -- an honest "no ceiling found", never a quiet
    fallback to the bracket's end.

    The predicate is assumed monotone: FAIL states do not un-fail as amplitude rises. That
    assumption is asserted at the answer by :func:`brackets_the_ceiling`, so a check that
    breaks it is reported rather than silently bisected through.
    """
    low = lower_uA
    if not no_check_fails(calculator, low):
        return 0.0
    if no_check_fails(calculator, upper_uA):
        return float("inf")

    high = upper_uA
    while True:
        middle = low + (high - low) / 2.0
        if middle <= low or middle >= high:
            return low
        if no_check_fails(calculator, middle):
            low = middle
        else:
            high = middle


def brackets_the_ceiling(calculator: Any, ceiling_uA: float) -> bool:
    """Whether ``ceiling_uA`` really is the boundary: it passes and its successor fails.

    A finiteness assertion is not enough. The naive ``headroom / excursion`` reading of the
    water-window margin is -21.095 uA on the plan's own case -- finite, and wrong.
    """
    import math

    if not math.isfinite(ceiling_uA):
        return False
    return no_check_fails(calculator, ceiling_uA) and not no_check_fails(
        calculator, math.nextafter(ceiling_uA, math.inf)
    )
