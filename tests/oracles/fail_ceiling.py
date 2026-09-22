"""The highest amplitude at which no check FAILs, found by binary search.

Computed without reading the package's answer. It consults exactly one thing: whether
``SafetyCalculator.assess().failed`` is empty, optionally restricted to a named set of
checks. It never touches ``limiting_current_uA``, ``limiting_mechanism``, ``margin``, or
any per-check maximum -- which is what makes it a legitimate expected value for all of
those.

Why this is needed. On the plan's worked example -- ``RingElectrode(330, 270, "Pt")`` at
80 uA, 200 us, 130 Hz -- the package reports a limiting current of 141.37 uA while two
checks are in a FAIL state at 80 uA. The true ceiling is 20.0 uA, so the headline is 7.07x
the highest amplitude at which nothing fails. A test written against the package's own
``min(...)`` expression cannot see that; this one can.

The search is over floats, not over a fixed tolerance: it narrows until the bracket is one
ulp wide, so it returns the exact boundary float rather than something near it.

Which checks count
------------------
The plan's D3(i) originally read "the highest amplitude at which no check FAILs". Ledger
84 restates it as "the highest amplitude at which no **LIMIT-BEARING** check FAILs", and
the qualifier changes the answer: ``Charge balance`` FAILs at every amplitude on a
monophasic protocol, being a property of the waveform rather than of the amplitude, so the
unrestricted ceiling there is ``0.0`` while the limit-bearing one is 15285.5 uA. Both
quantities are wanted -- ``0.0`` is what ``unsafe_at_any_amplitude`` is about and 15285.5
is what ``limiting_current_uA`` is about -- so ``names`` selects between them.

:data:`LIMIT_BEARING` is written out here rather than imported. The package defines its own
set in C1.3; an oracle that imported it would restate the package's partition of the checks
and could never disagree with it. ``tests/test_oracles.py`` asserts the two agree once C1.3
lands, which is a comparison of two independent statements rather than of one with itself.
Reading a check's *name* is not reading a number: no expected value here is derived from
anything the package computes.

The monotonicity assumption, and what happens when it is false
--------------------------------------------------------------
Bisection answers "the highest amplitude at which nothing fails" only if the passing
amplitudes are an interval reaching the bottom of the bracket: FAIL states do not un-fail
as amplitude rises. That is a property of the package's checks, not of this module, and it
is **not** always true. ``resting_potential_V = 0.9 V`` puts a Pt interface outside its own
+0.8 V window at rest, so a small cathodic pulse pulls it back INTO the window while a
large one breaches the charge limits: FAIL, then PASS, then FAIL. A reviewer's sweep of
6 804 configurations found 88 (1.3 %) with that shape.

So the bracket is **sampled before it is bisected**. ``fail_ceiling_uA`` walks a geometric
ladder across the whole bracket and holds it to the invariant **per check**: the probes at
which a given check FAILs must be a *suffix* of the ladder, because a check that fails at
one amplitude must fail at every higher one. A check that un-fails raises
:class:`NonMonotonePredicate` naming it and both amplitudes, rather than bisecting one band
and presenting its edge as the ceiling.

Per check, and not merely "the passing probes are a prefix", because the weaker form misses
a passing band narrower than one ladder step. Measured: ``resting_potential_V = 0.95`` on Pt
at 50 us passes over [59.91, 77.85] uA, a factor of 1.30 against the ladder's 1.78, so every
probe fails and the prefix rule concludes "no amplitude passes" when the ceiling is 78.54 uA.
The per-check form sees it anyway, because Water window FAILs at 56.2 uA and does not fail
at 100 uA. Over 1 152 swept configurations, 756 of which answer ``0.0``, the per-check form
catches **all 90** hidden bands a fine scan finds; the prefix form catches none of them.

This is what keeps ``0.0`` honest, and ``0.0`` is the one value that has to be. Under the
ledger 84 convention it is the *correct* answer for an amplitude-independent failure, so it
cannot simply be turned into an error. Under the per-check invariant it now carries a
witness: a probe that fails at the bottom of the bracket fails because some check fails
there, and that check's FAIL set being a suffix containing the first index means it fails at
**every** probe. :func:`amplitude_independent_failures` names it, so a caller can assert on
the check rather than on a bare zero. A caller that needs to tell ``0.0`` from a ceiling asks
:func:`brackets_the_ceiling`, which reports ``False`` for it instead of raising.

What the sampling cannot do is prove a negative: a band hiding between two probes with the
same checks failing on both sides would still be missed, and no finite ladder closes that.
The sweep above found no such case. The :func:`brackets_the_ceiling` call at the end of the
search is likewise not a second proof of monotonicity -- it re-evaluates the two probes the
bisection already established and so confirms boundary-ness, not maximality. It is there to
catch a predicate that changed under the search.
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Collection
from dataclasses import replace
from functools import cache
from typing import Any

# The searched amplitude is in microamps. One amp is far above any electrode this package
# describes, so a bracket that reaches it and still does not FAIL means there is no ceiling.
_DEFAULT_UPPER_uA = 1e6

# StimProtocol rejects a zero amplitude, so the bracket starts at a femtoamp instead. A
# protocol that already FAILs there has no usable amplitude at all, and the answer is 0.
_DEFAULT_LOWER_uA = 1e-12

# Probes per decade of the bracket. The default bracket spans 18 decades, so this is 73
# assessments before any bisection -- about 20 ms, against ~60 assessments for the
# bisection itself. It is the resolution at which a non-monotone band is visible: the
# 0.9 V resting-potential case passes over [9.83, 19.61] uA, a third of a decade, and is
# caught by two probes. A band narrower than one step is caught by the per-check invariant
# instead -- see the module docstring -- unless the same checks fail on both sides of it,
# which is the honest limit of sampling and not a bound this module can assert away.
_PROBES_PER_DECADE = 4

LIMIT_BEARING: frozenset[str] = frozenset(
    {
        "Shannon criterion",
        "Charge injection limit",
        "Water window",
        "Current density",
        "Microelectrode charge/phase",
        "Chronic degradation",
        "Compliance voltage",
    }
)
"""The seven checks that impose a ceiling on amplitude (fix plan D3, ledger 84).

Written out, never imported: see the module docstring. ``Charge balance`` and
``Validated envelope`` are excluded because their verdicts do not move with amplitude --
imbalance is a categorical property of the waveform and the envelope is a categorical
property of the parameter set.
"""


CARRIED_ARGUMENTS: frozenset[str] = frozenset(
    {
        "electrode",
        "protocol",
        "k",
        "material",
        "policy",
        "medium",
        "tissue_conductivity_S_per_m",
        "lead_resistance_ohm",
        "compliance_V",
        "measured_impedance_ohm",
        "resting_potential_V",
        "capacitance_uF_cm2",
    }
)
"""Every argument ``SafetyCalculator`` takes, as of the commit that froze this set.

:func:`rebuild_at` names all twelve, and checks this set against the live signature before
it builds anything. See :class:`ConstructorDrift` for why the naming alone is not enough.
"""


class ConstructorDrift(AssertionError):
    """``SafetyCalculator`` takes an argument this oracle does not carry, or has lost one.

    A new **required** parameter announces itself: ``rebuild_at`` would raise ``TypeError``
    at the call. A new **optional** one -- which is what the phases ahead add -- does not.
    It is silently defaulted, and the oracle then answers about a calculator that differs
    from the one it was handed in exactly the field the new phase introduced. The
    docstring claimed the explicit argument list protected against that; only this check
    does.
    """


class NonMonotonePredicate(AssertionError):
    """``assess().failed`` does not have the assumed shape, so no ceiling can be reported.

    Raised rather than returned: a bisection through a non-monotone predicate produces a
    plausible finite number that is not the ceiling, and a Phase 1 test asserting against
    it would pass for the wrong reason. An ``AssertionError`` because it is exactly the
    assumption this module documents itself as asserting.
    """


def rebuild_at(calculator: Any, current_uA: float) -> Any:
    """The same calculator with only the amplitude changed.

    Every construction argument is carried across explicitly, and the signature is
    checked against :data:`CARRIED_ARGUMENTS` before anything is built. A ``copy`` would be
    shorter and would silently inherit any future field; naming the arguments catches a new
    **required** one, and the signature check catches a new **optional** one, which naming
    alone does not -- see :class:`ConstructorDrift`.
    """
    from neurostim import SafetyCalculator

    _assert_constructor_is_frozen(SafetyCalculator)
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


def failing_checks(
    calculator: Any, current_uA: float, *, names: Collection[str] | None = None
) -> frozenset[str]:
    """The names of the checks in a FAIL state at ``current_uA``, restricted to ``names``.

    ``names = None`` means every check the assessment emits; pass :data:`LIMIT_BEARING`
    for the quantity ledger 84's D3(i) names. A name the assessment does not emit is a
    ``ValueError`` and not an empty restriction, because a misspelling would otherwise
    weaken the predicate to "never fails" and the search would answer ``inf``.

    Names, never numbers: this and :func:`no_check_fails` are the whole of what the oracle
    reads from the package.
    """
    assessment = rebuild_at(calculator, current_uA).assess()
    if names is not None:
        emitted = {check.name for check in assessment.checks}
        unknown = sorted(set(names) - emitted)
        if unknown:
            raise ValueError(
                f"no such check: {unknown}; this assessment emits {sorted(emitted)}"
            )
    return frozenset(
        check.name
        for check in assessment.failed
        if names is None or check.name in names
    )


def no_check_fails(
    calculator: Any, current_uA: float, *, names: Collection[str] | None = None
) -> bool:
    """Whether nothing among ``names`` is in a FAIL state at ``current_uA``."""
    return not failing_checks(calculator, current_uA, names=names)


def amplitude_independent_failures(
    calculator: Any,
    *,
    lower_uA: float = _DEFAULT_LOWER_uA,
    upper_uA: float = _DEFAULT_UPPER_uA,
    names: Collection[str] | None = None,
) -> tuple[str, ...]:
    """Checks that FAIL at every probe across the bracket, sorted.

    The witness for a ceiling of ``0.0``. Ledger 84's case -- ``Charge balance`` on a
    monophasic protocol -- is exactly this: a verdict that is a property of the waveform
    rather than of the amplitude. Asserting on the name is a far stronger statement than
    asserting on the zero, which is why ``fail_ceiling_uA`` never returns ``0.0`` without
    one of these existing.
    """
    ladder = probe_ladder(lower_uA, upper_uA)
    always = frozenset.intersection(
        *(failing_checks(calculator, amplitude, names=names) for amplitude in ladder)
    )
    return tuple(sorted(always))


def probe_ladder(
    lower_uA: float = _DEFAULT_LOWER_uA,
    upper_uA: float = _DEFAULT_UPPER_uA,
    *,
    per_decade: int = _PROBES_PER_DECADE,
) -> list[float]:
    """Geometric probe amplitudes across ``[lower_uA, upper_uA]``, both ends included.

    Geometric rather than linear because the bracket spans eighteen decades and the
    interesting amplitudes are microamps: a linear ladder would put every probe above
    100 kuA and see nothing.
    """
    if not (math.isfinite(lower_uA) and lower_uA > 0.0):
        raise ValueError(f"lower_uA must be finite and > 0, got {lower_uA!r}")
    if not (math.isfinite(upper_uA) and upper_uA > lower_uA):
        raise ValueError(f"upper_uA must be finite and > lower_uA, got {upper_uA!r}")

    steps = max(1, math.ceil(math.log10(upper_uA / lower_uA) * per_decade))
    ratio = (upper_uA / lower_uA) ** (1.0 / steps)
    ladder = [lower_uA * ratio**step for step in range(steps)]
    ladder.append(upper_uA)
    return ladder


def fail_ceiling_uA(
    calculator: Any,
    *,
    lower_uA: float = _DEFAULT_LOWER_uA,
    upper_uA: float = _DEFAULT_UPPER_uA,
    names: Collection[str] | None = None,
) -> float:
    """Largest amplitude at which no check in ``names`` is in a FAIL state.

    ``names = None`` considers every check; :data:`LIMIT_BEARING` gives the quantity
    ledger 84's D3(i) names, which is the one the package's reported limiting current is
    to be compared with.

    Returns ``0.0`` when no probe anywhere in the bracket passes -- which under the ledger
    84 convention is the correct answer for an amplitude-independent failure, and is the
    only thing ``0.0`` now means. Returns ``inf`` when nothing fails anywhere up to
    ``upper_uA`` -- an honest "no ceiling found", never a quiet fallback to the bracket's
    end. Raises :class:`NonMonotonePredicate` when the passing amplitudes are not a prefix
    of the probe ladder, or when the boundary it finds does not survive
    :func:`brackets_the_ceiling`.
    """
    ladder = probe_ladder(lower_uA, upper_uA)
    failing = [failing_checks(calculator, amplitude, names=names) for amplitude in ladder]
    _assert_each_check_fails_upwards(ladder, failing)

    passes = [not names_here for names_here in failing]
    first_fail = passes.index(False) if False in passes else len(passes)
    if first_fail == 0:
        # The invariant makes this a statement, not a shrug: the checks failing at the
        # bottom of the bracket have suffix FAIL sets containing index 0, so they fail at
        # every probe. amplitude_independent_failures names them.
        return 0.0
    if first_fail == len(passes):
        return float("inf")

    low, high = ladder[first_fail - 1], ladder[first_fail]
    while True:
        middle = low + (high - low) / 2.0
        if middle <= low or middle >= high:
            break
        if no_check_fails(calculator, middle, names=names):
            low = middle
        else:
            high = middle

    if not brackets_the_ceiling(calculator, low, names=names):
        raise NonMonotonePredicate(
            f"the bisection settled on {low!r} uA, which is not a boundary: it does not "
            f"both pass and fail one ulp above. The predicate changed under the search."
        )
    return low


def brackets_the_ceiling(
    calculator: Any, ceiling_uA: float, *, names: Collection[str] | None = None
) -> bool:
    """Whether ``ceiling_uA`` really is the boundary: it passes and its successor fails.

    A finiteness assertion is not enough. The naive ``headroom / excursion`` reading of the
    water-window margin is -21.095 uA on the plan's own case -- finite, and wrong.

    Total on every float, including the ones ``fail_ceiling_uA`` itself returns. ``0.0``
    and ``inf`` are answers, not boundaries, and a caller asking whether one brackets the
    ceiling must be told ``False`` rather than handed the ``ValueError`` that constructing
    a protocol at a non-positive amplitude raises.
    """
    if not math.isfinite(ceiling_uA) or ceiling_uA <= 0.0:
        return False
    return no_check_fails(calculator, ceiling_uA, names=names) and not no_check_fails(
        calculator, math.nextafter(ceiling_uA, math.inf), names=names
    )


@cache
def _assert_constructor_is_frozen(calculator_class: type) -> None:
    """Raise :class:`ConstructorDrift` unless the signature is the one that was frozen.

    Cached on the class: the bisection rebuilds a calculator ~135 times per call and the
    signature cannot change between two of them.
    """
    live = set(inspect.signature(calculator_class.__init__).parameters) - {"self"}
    added = sorted(live - CARRIED_ARGUMENTS)
    dropped = sorted(CARRIED_ARGUMENTS - live)
    if not added and not dropped:
        return
    raise ConstructorDrift(
        f"{calculator_class.__name__} no longer takes the arguments this oracle carries: "
        f"added {added}, dropped {dropped}. An argument that is not carried is left at its "
        f"default, so the oracle would answer about a different calculator from the one it "
        f"was handed. Carry it in rebuild_at and add it to CARRIED_ARGUMENTS."
    )


def _assert_each_check_fails_upwards(
    ladder: list[float], failing: list[frozenset[str]]
) -> None:
    """Every check's FAIL set must be a suffix of the ladder, or there is no ceiling.

    Stronger than requiring the passing probes to be a prefix, and the difference is the
    whole point: a passing band narrower than one ladder step leaves every probe failing,
    so the prefix form sees nothing, while the check that un-fails across the band is
    visible at the probes on either side of it.
    """
    for name in sorted(frozenset().union(*failing) if failing else frozenset()):
        fails_at = [name in here for here in failing]
        first = fails_at.index(True)
        recovered = next(
            (index for index in range(first + 1, len(fails_at)) if not fails_at[index]),
            None,
        )
        if recovered is None:
            continue
        raise NonMonotonePredicate(
            f"{name} FAILs at {ladder[first]:.6g} uA and does not FAIL at "
            f"{ladder[recovered]:.6g} uA. A check that fails at one amplitude must fail "
            f"at every higher one, so this bracket holds more than one passing band and "
            f"bisecting it would return the edge of whichever one the search landed in. "
            f"There is no ceiling to report."
        )
