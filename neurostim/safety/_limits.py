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
) -> float:
    """The largest float near ``value`` at which ``passes`` is still true.

    ``passes`` must be monotone-decreasing: true below the boundary, false above it. The
    result is asserted to *be* that boundary -- it passes and its successor does not -- so
    a predicate that violates the precondition raises :class:`LimitDidNotSettle` instead of
    yielding a plausible number from the middle of a non-monotone band.

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
            raise LimitDidNotSettle(
                f"{name}: the back-solved limit {value!r} still fails its own check "
                f"after {max_steps} steps down to {settled!r}. A one-ulp disagreement "
                f"between the back-solve and the forward comparison is what this walk is "
                f"for; this is a larger disagreement, so the two are not inverses of each "
                f"other and no value in between can be reported as the limit."
            )
        settled = math.nextafter(settled, -math.inf)
        steps += 1

    steps = 0
    while passes(math.nextafter(settled, math.inf)):
        if steps >= max_steps:
            raise LimitDidNotSettle(
                f"{name}: the back-solved limit {value!r} still passes its own check "
                f"{max_steps} steps above {settled!r}, so it is not the boundary and the "
                f"reported limit would be lower than the limit."
            )
        settled = math.nextafter(settled, math.inf)
        steps += 1

    return settled


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
