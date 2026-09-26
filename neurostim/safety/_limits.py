"""One contract for every reported limit: it passes its own check, and it prints low.

A limit is a promise -- programme this amplitude and the check passes. Two separate
defects broke that promise, and both are fixed here.

**The back-solve was not an exact inverse** (ledger 9). Each check computes its limit
through a different float association from the forward comparison, so the answer lands one
unit in the last place on either side of the true boundary. Measured over 9 materials x
3 policies x 2 polarities on a 100 um Pt disc: of 108 charge-injection and Shannon limits,
12 sit one ulp *above* their own boundary -- re-assessing there prints
"100 uC/cm^2 exceeds the 100 uC/cm^2 limit" -- and 4 sit one ulp *below* it. Compliance is
worse: over 36 (electrode, compliance voltage, pulse width) combinations, 6 limits fail
their own check and 14 more are not the boundary. :func:`floor_to_pass` settles the value
onto the boundary from whichever side it landed.

**Every render site rounded to nearest** (ledger 49). ``:.4g`` prints 141.37167 as
"141.4", and 141.4 uA FAILs the check whose maximum it claims to be. A maximum must floor.
:func:`format_limit` does, to four significant digits, and verifies that what it printed
parses back to something no larger than what it was given.

**The rule is about maxima, not about microamps** (ledger 96). Ledger 49 was scoped to
amplitude renders and the same defect survived a phase in other units: the in vivo derated
charge-injection limit printed "7.143" for 7.142857142857143 uC/cm^2 on four surfaces
including the PDF, and Butterwick's electroporation threshold -- a power law in pulse width
and electrode size, so round only by accident -- overstated on 32 of 56 swept (diameter,
pulse width) pairs, the worked example among them (0.3057 printed for 0.30567628563823 A/
cm^2). Hand :func:`format_limit` any quantity a reader must stay at or below.

*Applied* quantities keep round-to-nearest, deliberately. Flooring one understates what is
being delivered, which is the wrong direction for the number a limit is compared against.

The two are separate because they fail separately: a bit-exact back-solve still prints
wrong, and a floored string still overstates if the value behind it does.

What "floors" means here, precisely
-----------------------------------
Not "round down". The largest representable value that still passes, which is reached by
stepping *up* as often as by stepping down -- 4 of those 108 limits are below their
boundary, and reporting a limit lower than the limit is a different kind of wrong, not a
safe one, because the next commit takes a minimum over these values and a wrong minimum
picks the wrong binding mechanism.

The predicate and its precondition
----------------------------------
Every predicate handed to :func:`floor_to_pass` must be **monotone-decreasing in current**:
once it fails it must keep failing at every higher amplitude. That is asserted at the
returned point, both ways -- the value passes and its successor does not -- so a predicate
that is not monotone cannot quietly produce a plausible number. The one check in this
package whose predicate is *not* monotone is the water window with an out-of-window
resting potential, and the commit before this one made that input unconstructible rather
than leaving the precondition aspirational.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from decimal import ROUND_FLOOR, Decimal

STEP_BUDGET = 4
"""Floats a limit may be walked before the walk is treated as a failure, not a rounding.

Four, because the observed error is one ulp: the back-solve and the forward check differ
by one multiplication's association. A limit that needs five steps is not suffering from
float association -- it is a predicate that does not mean what the back-solve assumed, and
silently returning a value from the middle of that walk would hide it.
"""


CLIMB_TOLERANCE = 1e-9
"""How far above a back-solved limit the true boundary may be, relative to the value.

One of the two bounds on the *upward* search, where a step count does not work: see
:func:`_climb_to_boundary`. Generous against a plateau that scales with the value -- a few
floats is ~1e-15 of it -- and tight against a back-solve that does not invert its forward
comparison, which would be wrong by a relative amount set by the physics rather than by
the float grid.

It is *not* sufficient on its own, because not every plateau scales with the value: see
``plateau`` in :func:`floor_to_pass` and ``PLATEAU_ALLOWANCE``.
"""


PLATEAU_ALLOWANCE = 4
"""Declared plateaus the climb may cross before the seed is treated as simply wrong.

Four, for the reason ``STEP_BUDGET`` is four. The seed is built from the same quantities
the predicate compares -- for the water window, ``edge - resting`` and a multiply and a
divide by the same capacitance -- so each of them can displace it by its own rounding, and
a handful of plateaus is that rounding while a thousand is a different number.
"""


class LimitDidNotSettle(ArithmeticError):
    """A back-solved limit could not be walked onto its own check's boundary.

    Raised rather than returned. Returning the failing value would reinstate exactly the
    defect this module exists to fix -- a reported maximum that FAILs its own check -- and
    returning the last value tried would report a number with no stated relationship to
    the limit. ``ArithmeticError`` because the cause is the arithmetic, not the caller's
    input.
    """


def floor_to_pass(
    value: float,
    passes: Callable[[float], bool],
    *,
    name: str,
    max_steps: int = STEP_BUDGET,
    rel_tolerance: float = CLIMB_TOLERANCE,
    plateau: float = 0.0,
) -> float:
    """The largest float near ``value`` at which ``passes`` is still true.

    ``passes`` must be monotone-decreasing: true below the boundary, false above it. The
    result is asserted to *be* that boundary -- it passes and its successor does not -- so
    a predicate that violates the precondition raises :class:`LimitDidNotSettle` instead of
    yielding a plausible number from the middle of a non-monotone band.

    The two directions are bounded differently and deliberately: ``max_steps`` floats
    down, a distance up. See :func:`_climb_to_boundary` for why. A declared ``plateau``
    widens both, by the same distance, because a run the predicate cannot resolve can
    straddle the boundary from either side (see :func:`_descend_across_plateau`).

    ``plateau`` is the smallest change in ``value`` the predicate can resolve, in
    ``value``'s own units, and is 0.0 for a predicate that resolves every float. Only the
    caller knows it: it is a property of the check's arithmetic, not of the number handed
    over. Where the predicate adds the amplitude's effect to a *constant* -- the water
    window adds an excursion to a resting potential -- one ulp of that sum is a run of
    consecutive amplitudes the check cannot tell apart, its width is fixed by the constant
    rather than by the limit, and ``rel_tolerance`` alone is therefore guaranteed to be
    exceeded once the limit is small enough. See :func:`_climb_to_boundary`.

    ``name`` is the check the limit belongs to, and appears in the error. Non-finite and
    non-positive values are returned unchanged: ``inf`` means "no ceiling", ``0.0`` means
    "nothing is permitted", and neither is a float whose neighbours mean anything.
    """
    if not math.isfinite(value) or value <= 0.0:
        return value

    settled = value
    steps = 0
    while not passes(settled):
        if steps >= max_steps:
            return _descend_across_plateau(
                value, settled, passes, name=name, max_steps=max_steps, plateau=plateau
            )
        settled = math.nextafter(settled, -math.inf)
        steps += 1

    if passes(math.nextafter(settled, math.inf)):
        settled = _climb_to_boundary(
            settled, passes, name=name, rel_tolerance=rel_tolerance, plateau=plateau
        )
    return settled


def _descend_across_plateau(
    value: float,
    failing: float,
    passes: Callable[[float], bool],
    *,
    name: str,
    max_steps: int,
    plateau: float,
) -> float:
    """The boundary below a seed that the step budget could not reach, or a raise.

    A declared plateau can sit *above* the boundary as well as below it. Shannon's metric
    is ``log10(Q) + log10(Q/A)``, whose resolution is set by the larger addend, so above
    1e4 uC/cm^2 the seed ``sqrt(A * 10**k)`` lands five floats over the boundary inside a
    run of charges the predicate cannot tell apart -- and the four-step walk raised on
    input the package accepts (ledger 98). So the walk down may also go as far as
    ``PLATEAU_ALLOWANCE x plateau``, the distance the climb is already allowed, and then
    bisects onto the exact boundary.

    With no plateau declared nothing changes: the raise, and its message, are exactly the
    four-step budget's. A seed further above than both is still a back-solve that does not
    invert its comparison.
    """
    reach = PLATEAU_ALLOWANCE * plateau
    low = value - reach
    if reach <= 0.0 or low <= 0.0 or not passes(low):
        message = (
            f"{name}: the back-solved limit {value!r} still fails its own check "
            f"after {max_steps} steps down to {failing!r}. A one-ulp disagreement "
            f"between the back-solve and the forward comparison is what this walk is "
            f"for; this is a larger disagreement, so the two are not inverses of each "
            f"other and no value in between can be reported as the limit."
        )
        if reach > 0.0:
            message += (
                f" Nor does it pass within {reach!r} below, {PLATEAU_ALLOWANCE} times the "
                f"{plateau!r} the caller declared the check can resolve."
            )
        raise LimitDidNotSettle(message)

    high = failing
    while True:
        middle = low + (high - low) / 2.0
        if middle <= low or middle >= high:
            return low
        if passes(middle):
            low = middle
        else:
            high = middle


def _climb_to_boundary(
    value: float,
    passes: Callable[[float], bool],
    *,
    name: str,
    rel_tolerance: float,
    plateau: float = 0.0,
) -> float:
    """The largest float at or above ``value`` that still passes.

    Not budgeted in steps, which is the difference between this direction and the walk
    down, and the difference is not arbitrary. Walking *down* corrects a one-ulp
    disagreement between a back-solve and its forward comparison, and needing five steps
    means they are not inverses (ledger 9). Walking *up* crosses a plateau of the check's
    own making, and the plateau's length says nothing about the back-solve.

    The water window is the case that forced it. Its predicate is
    ``cathodic <= resting + excursion <= anodic``; with ``resting = -0.55 V`` on platinum
    the excursion at the boundary is 0.05 V, so the sum is two numbers of very different
    size and its ulp is an order of magnitude larger than the excursion's. A run of
    consecutive amplitudes then maps to the same peak float, all passing, and the seed
    sits more than four floats below the top of the run.

    **Why a relative bound alone cannot work.** That run's width in *current* is one ulp
    of the sum converted back through ``C x A / PW`` -- an absolute quantity, fixed by the
    resting potential rather than by the limit. Its width *relative to the limit* is
    therefore proportional to ``1 / limit``, and grows without bound as the resting
    potential approaches the window edge and the limit approaches zero. Any relative
    tolerance is exceeded somewhere inside the accepted inputs; raising it moves the
    headroom at which that happens and removes nothing. Measured at
    ``rel_tolerance = 1e-9``: 4487 of 70831 edge-clustered configurations raised on inputs
    the package accepts, and ``resting_potential_V = -0.59999999`` on a 100 um platinum
    disc -- 1e-8 V of headroom, well inside the window -- was one of them.

    So the budget is the larger of the two, and the caller supplies the second: an
    exponential bracket in ulps out to ``max(rel_tolerance x value,
    PLATEAU_ALLOWANCE x plateau)``, then a bisection onto the exact boundary. A seed
    further above than *both* is a wrong back-solve rather than a plateau, and still
    raises.
    """
    low = value
    offset = math.ulp(value)
    budget = max(abs(value) * rel_tolerance, PLATEAU_ALLOWANCE * plateau)
    while True:
        # `max` guarantees progress: `low + offset` can round back to `low`.
        high = max(low + offset, math.nextafter(low, math.inf))
        if not passes(high):
            break
        low = high
        offset *= 2.0
        if offset > budget:
            raise LimitDidNotSettle(
                f"{name}: the back-solved limit {value!r} still passes its own check at "
                f"{low!r}, which is further above it than {budget!r} -- the larger of "
                f"{rel_tolerance:g} of the value and {PLATEAU_ALLOWANCE} times the "
                f"{plateau!r} the caller declared the check can resolve. Neither float "
                f"granularity nor that plateau explains the gap, so the back-solve does "
                f"not invert its forward comparison and the reported limit would be "
                f"materially lower than the limit."
            )

    while True:
        middle = low + (high - low) / 2.0
        if middle <= low or middle >= high:
            return low
        if passes(middle):
            low = middle
        else:
            high = middle


def format_limit(value: float, sig: int = 4) -> str:
    """Render a limit to ``sig`` significant digits, never rounding it up.

    ``f"{141.37166941154072:.4g}"`` is ``"141.4"``, and programming 141.4 uA FAILs the
    check whose maximum it claims to be (ledger 49). This prints ``"141.3"``.

    The flooring is done in decimal, on the float's exact value, so it does not inherit a
    second rounding from the binary representation. What is then verified is the property
    a reader actually relies on: the string, parsed back to a float, is no larger than the
    value it describes. If the decimal nearest the floored digits happens to round up past
    the input -- possible when the input sits less than half an ulp above a ``sig``-digit
    decimal -- one more quantum comes off.

    Fixed or scientific notation on the same threshold ``:.{sig}g`` uses, so 15285.5 still
    reads "1.528e+04" -- but trailing zeros are kept, because ``sig`` significant digits is
    the promise: 212.0575 prints "212.0", not "212", and a limit of exactly 20 prints
    "20.00". Non-finite values are passed through untouched: ``inf`` means "no ceiling
    found" and must not become a number.
    """
    if not math.isfinite(value) or value == 0.0:
        return f"{value:.{sig}g}"

    exact = Decimal(value)
    quantum = Decimal(1).scaleb(exact.adjusted() - sig + 1)
    floored = exact.quantize(quantum, rounding=ROUND_FLOOR)
    text = _render(floored, exact.adjusted(), sig)
    if float(text) > value:
        # The input sat less than half an ulp above a `sig`-digit decimal, so the nearest
        # float to the floored digits is above it after all. One more quantum off.
        floored -= quantum
        text = _render(floored, floored.adjusted(), sig)
    return text


def _render(floored: Decimal, exponent: int, sig: int) -> str:
    """``floored`` at exactly ``sig`` significant digits, trailing zeros kept.

    The fixed/scientific threshold is ``:.{sig}g``'s own, so reports do not change shape.
    """
    if -4 <= exponent < sig:
        return f"{floored:.{max(sig - 1 - exponent, 0)}f}"
    # Through the float, so the exponent is zero-padded the way ``%e`` writes it
    # ("1.528e+04", not Decimal's "1.528e+4"). The digits are already settled.
    return f"{float(floored):.{sig - 1}e}"


def format_exceeding(applied: float, bound_text: str, sig: int = 4) -> str:
    """Render an applied value that exceeds a bound so it reads as exceeding it.

    An exceedance sentence prints two numbers, and when they sit close both rounded to the
    same digits: "100 uC/cm^2 exceeds the 100.0 uC/cm^2 limit", "k = 1.50 exceeds the 1.50
    threshold" (ledger 50). The applied value keeps round-to-nearest -- flooring it would
    understate what is delivered -- at ``sig`` significant digits, and gains digits only
    until what it prints parses strictly above ``bound_text``, the bound as printed.
    Called only where ``applied`` truly exceeds the bound, so enough digits always do.
    """
    if not math.isfinite(applied):
        return f"{applied:.{sig}g}"
    bound = float(bound_text)
    for digits in range(sig, 18):
        text = f"{applied:.{digits}g}"
        if float(text) > bound:
            return text
    return repr(applied)


def format_setting(value: float, decimals: int = 2) -> str:
    """A user's setting -- a threshold such as Shannon's ``k`` -- exactly as given.

    At least ``decimals`` places, and as many more as it takes for the text to parse back
    to the value: ``1.5`` prints "1.50", ``1.749`` prints "1.749". ``:.2f`` printed 1.749
    as "1.75", a threshold rounded up past the one applied (ledger 163).
    """
    if not math.isfinite(value):
        return repr(value)
    for places in range(decimals, 18):
        text = f"{value:.{places}f}"
        if float(text) == value:
            return text
    return repr(value)


def format_against(applied: float, bound_text: str, *, exceeds: bool, decimals: int = 2) -> str:
    """An applied value beside a printed bound, on the side of it the verdict is on.

    ``decimals`` places, more as needed, until the text parses strictly above
    ``bound_text`` when ``exceeds`` and at or below it otherwise (ledgers 50, 163). Called
    only where ``applied`` truly is on that side, so enough places always do.
    """
    if not math.isfinite(applied):
        return repr(applied)
    bound = float(bound_text)
    for places in range(decimals, 18):
        text = f"{applied:.{places}f}"
        if (float(text) > bound) if exceeds else (float(text) <= bound):
            return text
    return repr(applied)

