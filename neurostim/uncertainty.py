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
"""

from __future__ import annotations

import math
from dataclasses import dataclass


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
        if sd < 0:
            raise ValueError(f"sd must be >= 0, got {sd}")
        return cls(mean - k * sd, mean + k * sd)

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
        if isinstance(other, Interval):
            candidates = [
                op(self.low, other.low),
                op(self.low, other.high),
                op(self.high, other.low),
                op(self.high, other.high),
            ]
        else:
            candidates = [op(self.low, other), op(self.high, other)]
        return Interval(min(candidates), max(candidates))

    def __add__(self, other) -> Interval:
        return self._binary(other, lambda a, b: a + b)

    __radd__ = __add__

    def __sub__(self, other) -> Interval:
        return self._binary(other, lambda a, b: a - b)

    def __rsub__(self, other) -> Interval:
        return Interval.exact(other) - self

    def __mul__(self, other) -> Interval:
        return self._binary(other, lambda a, b: a * b)

    __rmul__ = __mul__

    def __truediv__(self, other) -> Interval:
        divisor = other if isinstance(other, Interval) else Interval.exact(other)
        if divisor.contains(0.0):
            raise ZeroDivisionError(
                f"cannot divide by an interval spanning zero: "
                f"[{divisor.low}, {divisor.high}]"
            )
        return self._binary(other, lambda a, b: a / b)

    def __rtruediv__(self, other) -> Interval:
        return Interval.exact(other) / self

    def __neg__(self) -> Interval:
        return Interval(-self.high, -self.low)

    def scaled(self, factor: float) -> Interval:
        """Multiply both bounds by a scalar."""
        return self * factor

    def sqrt(self) -> Interval:
        """Element-wise square root; requires a non-negative interval."""
        if self.low < 0:
            raise ValueError(f"sqrt of an interval with a negative bound: {self}")
        return Interval(math.sqrt(self.low), math.sqrt(self.high))

    # --- rendering ------------------------------------------------------------

    def describe(self, unit: str = "", fmt: str = ".4g") -> str:
        """Human-readable rendering, collapsing to one number when exact."""
        suffix = f" {unit}" if unit else ""
        if self.is_exact:
            return f"{self.low:{fmt}}{suffix}"
        return f"{self.low:{fmt}}-{self.high:{fmt}}{suffix}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.describe()


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
