"""Interval arithmetic for propagating published ranges through to final limits.

The problem this solves
-----------------------
Nearly every constant in this package is a range, not a number. Cogan gives platinum as
0.05-0.15 mC/cm^2 -- a factor of three. Collapsing that to one value with a ``policy``
setting and reporting a single current limit hides the fact that the honest answer is
"somewhere between 71 and 212 microamps, and which end you believe depends on whether
your pulsing is anodic-first".

An :class:`Interval` carries both ends through the arithmetic so the final limit can be
reported the same way the source reported it.

Scope and its limits
--------------------
This is **interval arithmetic**, not uncertainty quantification. It answers "what is the
range of outcomes if every input sits anywhere in its range", which is deliberately
pessimistic: it assumes inputs can conspire at their extremes simultaneously, and it
does not track correlation between them. For a probabilistic answer, use the standard
deviations and sample sizes recorded on the source data (for example
``TissueThermalProperties.uncertainty``) with a Monte Carlo draw instead.

Interval arithmetic also suffers the dependency problem: ``x - x`` is not zero when
computed as an interval, because each occurrence is treated as independent. Nothing here
subtracts an interval from itself, but keep it in mind before extending this module.
``x * x`` is the same problem, and :meth:`Interval.square` (``x ** 2``) is the answer to
it: the product of an interval with itself returned [-1, 1] for [-1, 1] (ledger 23).
General dependency tracking is out of scope.

Outward rounding
----------------
Every arithmetic result that floating point had to round is widened by one unit in the
last place, down at the low end and up at the high end -- the four operations, integer
powers, :meth:`Interval.sqrt` and :meth:`Interval.from_mean_sd` -- so the interval does
contain every possible result: ``Interval(0.1, 0.1) * 3`` used to be exactly 0.30000000000000004,
which excludes 0.3 (ledger 26). A result the floats represent exactly -- checked with
:class:`fractions.Fraction` -- is left as it is, so exact inputs give exact outputs.
"""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Interval:
    """A closed interval ``[low, high]`` of possible values."""

    low: float
    high: float

    def __post_init__(self) -> None:
        if math.isnan(self.low) or math.isnan(self.high):
            raise ValueError(f"Interval bounds must not be NaN, got [{self.low}, {self.high}]")
        if self.high < self.low:
            raise ValueError(
                f"Interval high ({self.high}) must be >= low ({self.low})"
            )

    # --- constructors ---------------------------------------------------------

    @classmethod
    def exact(cls, value: float) -> Interval:
        """A degenerate interval representing a known value."""
        return cls(value, value)

    @classmethod
    def from_mean_sd(cls, mean: float, sd: float, k: float = 1.0) -> Interval:
        """``mean +/- k*sd``. ``k=1`` is roughly 68 % for a normal spread, ``k=2`` 95 %."""
        if not math.isfinite(sd) or sd < 0:
            raise ValueError(f"sd must be finite and >= 0, got {sd!r}")
        # Its own message: a negative k used to fail on bound ordering (ledger 31).
        if not math.isfinite(k) or k < 0:
            raise ValueError(f"k must be finite and >= 0, got {k!r}")
        # The bounds computed exactly and rounded outward, as the arithmetic is: two float
        # roundings could leave either end inside the true range (ledger 172).
        if not math.isfinite(mean):
            return cls(mean - k * sd, mean + k * sd)
        spread = Fraction(k) * Fraction(sd)
        return cls(
            _round_outward(Fraction(mean) - spread, down=True),
            _round_outward(Fraction(mean) + spread, down=False),
        )

    # --- properties -----------------------------------------------------------

    @property
    def width(self) -> float:
        """``high - low``."""
        return self.high - self.low

    @property
    def midpoint(self) -> float:
        """Arithmetic centre."""
        return 0.5 * (self.low + self.high)

    @property
    def is_exact(self) -> bool:
        """Whether the interval is a single point."""
        return self.low == self.high

    @property
    def fold_range(self) -> float:
        """``high / low``: how many fold the published range spans.

        Infinite when the low end is zero, which is itself worth surfacing.
        """
        if self.low == 0:
            return math.inf if self.high > 0 else 1.0
        return self.high / self.low

    def contains(self, value: float) -> bool:
        """Whether a value lies inside the interval."""
        return self.low <= value <= self.high

    def overlaps(self, other: Interval) -> bool:
        """Whether two intervals intersect."""
        return self.low <= other.high and other.low <= self.high

    # --- arithmetic -----------------------------------------------------------

    def _binary(self, other, op) -> Interval:
        pairs = (
            [(a, b) for a in (self.low, self.high) for b in (other.low, other.high)]
            if isinstance(other, Interval)
            else [(self.low, other), (self.high, other)]
        )
        results = [(op(a, b), a, b) for a, b in pairs]
        low = min(results, key=lambda item: item[0])
        high = max(results, key=lambda item: item[0])
        return Interval(
            _outward(low[0], op, low[1], low[2], down=True),
            _outward(high[0], op, high[1], high[2], down=False),
        )

    def __add__(self, other) -> Interval:
        return self._binary(other, operator.add)

    __radd__ = __add__

    def __sub__(self, other) -> Interval:
        return self._binary(other, operator.sub)

    def __rsub__(self, other) -> Interval:
        return Interval.exact(other) - self

    def __mul__(self, other) -> Interval:
        return self._binary(other, operator.mul)

    __rmul__ = __mul__

    def __truediv__(self, other) -> Interval:
        divisor = other if isinstance(other, Interval) else Interval.exact(other)
        if divisor.contains(0.0):
            raise ZeroDivisionError(
                f"cannot divide by an interval spanning zero: "
                f"[{divisor.low}, {divisor.high}]"
            )
        return self._binary(other, operator.truediv)

    def __rtruediv__(self, other) -> Interval:
        return Interval.exact(other) / self

    def __neg__(self) -> Interval:
        return Interval(-self.high, -self.low)

    def scaled(self, factor: float) -> Interval:
        """Multiply both bounds by a scalar."""
        return self * factor

    def square(self) -> Interval:
        """``x ** 2`` over the interval: ``[0, max^2]`` when it spans zero.

        Not ``self * self``, which treats the two factors as independent and gave
        [-1, 1] for [-1, 1] -- a negative lower bound on a square (ledger 23).
        """
        return self._power(2)

    def __pow__(self, exponent: int) -> Interval:
        """A non-negative integer power, with the dependency of the factors respected."""
        if not isinstance(exponent, int) or exponent < 0:
            raise ValueError(f"only non-negative integer powers, got {exponent!r}")
        if exponent == 0:
            return Interval.exact(1.0)
        return self._power(exponent)

    def _power(self, exponent: int) -> Interval:
        """Odd powers are monotone, so the ends map to the ends; an even power of an
        interval spanning zero has zero as its minimum. Both ends rounded outward."""

        def raised(x: float, *, down: bool) -> float:
            value = x**exponent
            if not math.isfinite(value) or Fraction(x) ** exponent == Fraction(value):
                return value
            return math.nextafter(value, -math.inf if down else math.inf)

        if exponent % 2:
            return Interval(raised(self.low, down=True), raised(self.high, down=False))
        if self.low <= 0.0 <= self.high:
            return Interval(
                0.0, max(raised(self.low, down=False), raised(self.high, down=False))
            )
        near, far = sorted((self.low, self.high), key=abs)
        return Interval(raised(near, down=True), raised(far, down=False))

    def sqrt(self) -> Interval:
        """Element-wise square root; requires a non-negative interval."""
        if self.low < 0:
            raise ValueError(f"sqrt of an interval with a negative bound: {self}")
        # Rounded outward like the arithmetic: math.sqrt rounds to nearest, which put the
        # low end above the true root in about half of all cases (ledger 172).
        low, high = math.sqrt(self.low), math.sqrt(self.high)
        if math.isfinite(low) and Fraction(low) ** 2 > Fraction(self.low):
            low = math.nextafter(low, -math.inf)
        if math.isfinite(high) and Fraction(high) ** 2 < Fraction(self.high):
            high = math.nextafter(high, math.inf)
        return Interval(low, high)

    # --- rendering ------------------------------------------------------------

    def describe(self, unit: str = "", fmt: str = ".4g", *, floor: bool = False) -> str:
        """Human-readable rendering, collapsing to one number when exact.

        ``floor`` is for intervals whose ends are *limits*. ``:.4g`` rounds to nearest,
        which rounds a maximum up: the worked example's limiting-current interval printed
        "141.4-212.1 uA" for ends of 141.37167 and 212.05750, and programming either
        printed figure FAILs the check it is the maximum for (ledger 49). With ``floor``
        both ends go through ``safety._limits.format_limit`` instead, giving
        "141.3-212.0 uA". It is opt-in because most intervals here are measurements or
        published ranges, and rounding a measurement down is not more conservative -- it
        is just wrong.
        """
        suffix = f" {unit}" if unit else ""

        def render(value: float) -> str:
            if not floor:
                return f"{value:{fmt}}"
            # Imported here, not at module scope: `neurostim.safety` imports this module,
            # so a top-level import would close the cycle.
            from .safety._limits import format_limit

            return format_limit(value)

        if self.is_exact:
            return f"{render(self.low)}{suffix}"
        return f"{render(self.low)}-{render(self.high)}{suffix}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.describe()


def _round_outward(exact: Fraction, *, down: bool) -> float:
    """The float nearest ``exact``, one ulp further out if that lies inside it."""
    value = float(exact)
    if (Fraction(value) > exact) if down else (Fraction(value) < exact):
        return math.nextafter(value, -math.inf if down else math.inf)
    return value


def _outward(value: float, op, a: float, b: float, *, down: bool) -> float:
    """``value`` = ``op(a, b)`` in floats, one ulp outward if floats rounded it."""
    if not math.isfinite(value) or not (math.isfinite(a) and math.isfinite(b)):
        return value
    if op(Fraction(a), Fraction(b)) == Fraction(value):
        return value
    return math.nextafter(value, -math.inf if down else math.inf)


def combine(intervals: list[Interval]) -> Interval:
    """Tightest interval containing every input, i.e. the union's hull."""
    if not intervals:
        raise ValueError("combine() needs at least one interval")
    return Interval(min(i.low for i in intervals), max(i.high for i in intervals))


def intersect(intervals: list[Interval]) -> Interval | None:
    """Intersection of every input, or ``None`` when they do not all overlap.

    Used to find the binding limit when several constraints are each expressed as a
    range: the admissible set is where they agree.
    """
    if not intervals:
        raise ValueError("intersect() needs at least one interval")
    low = max(i.low for i in intervals)
    high = min(i.high for i in intervals)
    return Interval(low, high) if high >= low else None


def most_restrictive(intervals: list[Interval]) -> Interval:
    """Element-wise minimum of several limits.

    The binding constraint is the smallest at each end: if the Shannon limit is
    595 uA exactly and the material limit is 71-212 uA, the usable amplitude is
    71-212 uA.
    """
    if not intervals:
        raise ValueError("most_restrictive() needs at least one interval")
    return Interval(
        min(i.low for i in intervals), min(i.high for i in intervals)
    )
