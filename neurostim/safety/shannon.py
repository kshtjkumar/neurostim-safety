"""The Shannon (1992) charge / charge-density damage criterion.

Merrill et al. (2005) state the relation as their equation (5.1):

.. math::

    \\log_{10}\\!\\left(\\frac{Q}{A}\\right) = k - \\log_{10}(Q)

with ``Q`` the charge per phase in uC/phase, ``Q/A`` the charge density per phase in
uC/cm^2 per phase, and ``2.0 > k > 1.5`` fit to the empirical data. Rearranged, the
metric evaluated for a given protocol is

.. math::

    k = \\log_{10}(Q) + \\log_{10}(Q/A) = \\log_{10}\\!\\left(\\frac{Q^2}{A}\\right)

and the maximum charge per phase permitted at a chosen ``k`` is
``Q_max = sqrt(A * 10^k)``.

What the criterion actually rests on
------------------------------------
Shannon reprocessed the McCreery et al. (1990) cat parietal cortex histology, together
with data from Yuen et al. (1981), Agnew et al. (1989) and Bhargava (1993). Points
above the line showed damage; points below did not. Consequences worth keeping in view:

- It is an **empirical separatrix through animal histology**, not a mechanism. It does
  not distinguish electrochemical from mass-action injury.
- The underlying data are largely **cortical surface and penetrating macroelectrodes**.
  Cogan (2008) notes that most tissue-damage thresholds were determined at frequencies
  well below those used clinically, so extrapolating to high-rate protocols is
  unsupported by the fit itself.
- ``k`` is a **choice**, not a measurement. 1.5 is the conservative edge of the fitted
  band and 2.0 the permissive edge.
- It is written in **area** and fit on **discs**, while Shannon himself states that the
  safe limit is "linearly related to electrode diameter, not electrode area", because
  charge builds up at the edges. A ring or a band of the same area as a disc has a very
  different perimeter and gets the same limit. No source here gives a perimeter form, so
  the number is unchanged, but :func:`geometry_caveat` makes the assessment say so, never
  return an unqualified PASS for a non-disc geometry, and mark the limit provisional
  (ledger 12).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..units import charge_uC
from ._limits import floor_to_pass, format_against, format_limit, format_setting

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance
    from ..geometry.base import Electrode
    from ..uncertainty import Interval

K_SHANNON = 1.5
"""The value Shannon (1992) actually recommends and uses throughout his own paper.

Two direct statements from the primary text:

    "The curve for k = 1.5 defines a set of parameters where no damage was observed
    and is used for all computations that follow."

    "For the stimulus conditions of McCreery et al., k = 1.5 is a conservative limit
    and has been used in all calculations in this report."
"""

K_CONSERVATIVE = K_SHANNON
"""Alias for :data:`K_SHANNON`."""

K_MODERATE = 1.7
"""Lowest of the three curves drawn in Merrill et al. (2005) Fig. 8.

Merrill's figure spans k = 1.7, 1.85 and 2.0. That is a redrawing of Shannon's
relation, not a second endorsement of those values as safe.
"""

K_DAMAGE_OBSERVED = 2.0
"""**Damage was observed at this value.** Not a safety limit.

Shannon (1992) is explicit:

    "When k = 2, the straight line falls in an area where damage was observed. If this
    line were used to define the limit of safe stimulation, some stimuli would be
    expected to cause damage."

Merrill et al. quote the band as ``2.0 > k > 1.5``, which describes the family of lines
Shannon drew (his Fig. 1 shows k = 1.0, 1.5 and 2.0). It is not a statement that 2.0 is
an acceptable operating point, and this package does not treat it as one.
"""

K_PERMISSIVE = K_DAMAGE_OBSERVED
"""Deprecated alias for :data:`K_DAMAGE_OBSERVED`, kept for 0.2.x compatibility.

The old name implied 2.0 was merely the least protective *safe* choice. It is not.
"""

K_DEFAULT = K_SHANNON
"""Package default: 1.5, as Shannon recommends.

Changed from 1.7 in 0.4.0 after reading the primary source. 1.7 came from Merrill's
figure and had no safety justification behind it; at 1.7 a protocol is permitted about
1.6x the charge that Shannon's own conservative line allows.
"""

K_BOUNDS = (K_SHANNON, K_DAMAGE_OBSERVED)
"""Full span of lines Shannon drew, from conservative-safe to damage-observed.

Used by the interval propagation to show how much the choice of ``k`` moves the answer.
The upper end is **not** safe; it is the boundary of the region where McCreery saw
injury.
"""

# --- conditions under which the underlying data were collected ---------------------

FIT_PULSE_WIDTH_US = 400.0
"""Pulse width of every point in the McCreery dataset behind the fit."""

FIT_FREQUENCY_HZ = 50.0
"""Pulse rate of every point in the McCreery dataset behind the fit."""

FIT_DURATION_H = 7.0
"""Continuous stimulation duration in the McCreery experiments."""

FIT_PREPARATION = "adult cat parietal cortex, surface and penetrating electrodes"
"""Preparation the fit is derived from."""


def geometry_caveat(electrode: Electrode | None) -> str:
    """Why the criterion's number is uncertain for this geometry; empty for a real disc.

    Shannon (1992): "the limit of safe stimulation is linearly related to electrode
    diameter, not electrode area. This result is probably due to the charge 'building up'
    at the edges, to create higher charge densities around the perimeter of the
    electrode." The fit is in area and on disc-shaped surface electrodes, so any other
    shape -- including a disc that stands in for one by area -- gets an extrapolated
    limit.
    """
    from ..geometry.planar import DiscElectrode

    if electrode is None:
        return ""
    if isinstance(electrode, DiscElectrode) and electrode.access_resistance_is_exact:
        return ""
    return (
        f"GEOMETRY: the criterion was fit on disc-shaped electrodes and is written in "
        f"area, while Shannon (1992) states the safe limit is linearly related to electrode "
        f"diameter, not area, because charge builds up at the edges. This "
        f"{electrode.shape_name} has the area of a disc but not its perimeter, so the "
        f"limit is an extrapolation."
    )


def validate_k(k: float) -> None:
    """Raise if ``k`` is not a finite number; warn-worthy values are handled elsewhere."""
    if not math.isfinite(k):
        raise ValueError(f"Shannon k must be finite, got {k!r}")


def k_is_supported(k: float) -> bool:
    """Whether ``k`` lies inside the 1.5-2.0 span of lines Shannon drew.

    Being inside the span does **not** mean being safe: the upper end is where McCreery
    observed damage. Use :func:`k_is_conservative` for the safety question.
    """
    return K_SHANNON <= k <= K_DAMAGE_OBSERVED


def k_is_conservative(k: float) -> bool:
    """Whether ``k`` is at or below the value Shannon recommends as safe (1.5)."""
    return k <= K_SHANNON


def k_warning(k: float) -> str:
    """A warning string for a chosen ``k``, or empty when it is at Shannon's limit.

    Anything above 1.5 permits more charge than the primary source endorses, and the
    message says by how much: the permitted charge scales as ``10^(k/2)``.
    """
    if k <= K_SHANNON:
        return ""
    excess = 10 ** ((k - K_SHANNON) / 2.0)
    if k >= K_DAMAGE_OBSERVED:
        return (
            f"k = {format_setting(k)} is at or above 2.0, where Shannon (1992) states damage was "
            f"observed; it permits {excess:.2f}x the charge of his recommended 1.5 "
            f"line and is not a safety limit"
        )
    return (
        f"k = {format_setting(k)} exceeds the 1.5 that Shannon (1992) recommends and uses "
        f"throughout; it permits {excess:.2f}x the charge of that line"
    )


def conditions_warning(pulse_width_us: float, frequency_hz: float | None = None) -> str:
    """Warn when a protocol sits far from the conditions the fit was derived under.

    Shannon states the limitation directly: "At the present time we do not adequately
    know how to extrapolate from this data to predict damage thresholds for longer
    stimulation durations, or for higher stimulation rates, or even for different pulse
    durations."
    """
    parts: list[str] = []
    pw_fold = max(
        pulse_width_us / FIT_PULSE_WIDTH_US, FIT_PULSE_WIDTH_US / pulse_width_us
    )
    if pw_fold > 2.0:
        parts.append(
            f"pulse width {pulse_width_us:g} us is {pw_fold:.1f}x from the "
            f"{FIT_PULSE_WIDTH_US:g} us of the underlying data"
        )
    if frequency_hz is not None:
        f_fold = max(
            frequency_hz / FIT_FREQUENCY_HZ, FIT_FREQUENCY_HZ / frequency_hz
        )
        if f_fold > 2.0:
            parts.append(
                f"rate {frequency_hz:g} Hz is {f_fold:.1f}x from the "
                f"{FIT_FREQUENCY_HZ:g} Hz of the underlying data"
            )
    if not parts:
        return ""
    return (
        f"{'; '.join(parts)}. Shannon states that extrapolation to different pulse "
        f"durations, rates or exposure times is not established."
    )


def shannon_k(charge_per_phase_uC: float, area_cm2: float) -> float:
    """Evaluate the Shannon metric ``k = log10(Q^2 / A)`` for a protocol.

    Compare the result against a chosen threshold: a protocol at ``k = 1.9`` sits above
    the conservative 1.5 line and below the permissive 2.0 line.

    Computed as ``log10(Q) + log10(Q/A)``, Merrill's form, and not as one log of the
    quotient. The two are equal in exact arithmetic but not in floats: the sum rounds at
    the resolution of its larger addend, which is what :func:`_metric_plateau_uC` declares.

    Raises
    ------
    ValueError
        If either argument is non-positive. The metric involves ``log10`` of both the
        charge and the charge density, so zero or negative values have no meaning here
        rather than producing a domain error deeper in the call stack.
    """
    if not math.isfinite(charge_per_phase_uC) or charge_per_phase_uC <= 0:
        raise ValueError(
            f"charge_per_phase_uC must be finite and > 0 to evaluate the Shannon "
            f"metric, got {charge_per_phase_uC!r}"
        )
    if not math.isfinite(area_cm2) or area_cm2 <= 0:
        raise ValueError(
            f"area_cm2 must be finite and > 0, got {area_cm2!r}"
        )
    charge_density = charge_per_phase_uC / area_cm2
    return math.log10(charge_per_phase_uC) + math.log10(charge_density)


def _metric_plateau_uC(charge_per_phase_uC: float, area_cm2: float) -> float:
    """The smallest change in charge :func:`shannon_k` can resolve near ``charge``.

    ``shannon_k`` is a *sum* of two logs, ``log10(Q) + log10(Q/A)``, so its rounding is set
    by the larger addend and not by the result ``k``: above 1e4 uC/cm^2 ``log10(Q/A)``
    sits in the ``[4, 8)`` binade, whose ulp is four times that of ``k`` in ``[1, 2)``. One
    ulp of that addend, carried back through ``dk/dQ = 2 / (Q ln 10)``, is a run of
    charges the metric cannot tell apart -- and the seed can land on the far side of it
    from the boundary (ledger 98). Declared to :func:`floor_to_pass` as its ``plateau``.
    """
    larger = max(
        abs(math.log10(charge_per_phase_uC)),
        abs(math.log10(charge_per_phase_uC / area_cm2)),
    )
    return math.ulp(larger) * charge_per_phase_uC * math.log(10.0) / 2.0


def shannon_max_charge_uC(area_cm2: float, k: float = K_DEFAULT) -> float:
    """Maximum charge per phase at a given ``k``: ``Q_max = sqrt(A * 10^k)``.

    Settled onto the boundary of the forward metric: ``sqrt`` is not the bit-exact inverse
    of ``log10(Q^2/A)``, so the closed form can land one ulp on either side of the largest
    charge that still satisfies ``shannon_k(Q, A) <= k`` (ledger 9) -- or several, where
    the metric's own resolution is coarser than a float of ``Q`` (ledger 98, see
    :func:`_metric_plateau_uC`).
    """
    validate_k(k)
    if not math.isfinite(area_cm2) or area_cm2 <= 0:
        raise ValueError(f"area_cm2 must be finite and > 0, got {area_cm2!r}")
    seed = math.sqrt(area_cm2 * 10.0**k)
    return floor_to_pass(
        seed,
        lambda charge_uC_: shannon_k(charge_uC_, area_cm2) <= k,
        name="Shannon criterion",
        plateau=_metric_plateau_uC(seed, area_cm2),
    )


def shannon_max_charge_density_uC_cm2(
    area_cm2: float, k: float = K_DEFAULT
) -> float:
    """Charge density corresponding to :func:`shannon_max_charge_uC`.

    Equal to ``sqrt(10^k / A)``, so it *rises* as area falls: a microelectrode is
    permitted a far higher charge density than a macroelectrode, which is the whole
    point of the criterion.
    """
    return shannon_max_charge_uC(area_cm2, k) / area_cm2


def shannon_max_current_uA(
    area_cm2: float, pulse_width_us: float, k: float = K_DEFAULT
) -> float:
    """Maximum leading-phase current at a given area, pulse width and ``k``.

    Settled onto the boundary of the forward check rather than returned as computed: the
    back-solve divides where :func:`shannon_k` multiplies and takes a log, so the two are
    not bit-exact inverses and the answer can land one ulp on either side (ledger 9).
    """
    if not math.isfinite(pulse_width_us) or pulse_width_us <= 0:
        raise ValueError(
            f"pulse_width_us must be finite and > 0, got {pulse_width_us!r}"
        )
    max_charge = shannon_max_charge_uC(area_cm2, k)
    return floor_to_pass(
        max_charge / (pulse_width_us * 1e-6),
        lambda current_uA: shannon_k(charge_uC(current_uA, pulse_width_us), area_cm2)
        <= k,
        name="Shannon criterion",
        # The metric's resolution in charge, carried to current by the same division.
        plateau=_metric_plateau_uC(max_charge, area_cm2) / (pulse_width_us * 1e-6),
    )


@dataclass(frozen=True)
class ShannonResult:
    """Outcome of evaluating the Shannon criterion for one protocol and electrode."""

    k_metric: float
    k_threshold: float
    charge_per_phase_uC: float
    charge_density_uC_cm2: float
    max_charge_uC: float
    max_current_uA: float
    area_cm2: float

    @property
    def passes(self) -> bool:
        """Whether the protocol sits at or below the chosen threshold line."""
        return self.k_metric <= self.k_threshold

    @property
    def margin_db(self) -> float:
        """Headroom in decades of ``Q^2/A``: positive is below the line."""
        return self.k_threshold - self.k_metric

    @property
    def current_margin(self) -> float:
        """Ratio of the permitted current to the requested current.

        Values above 1 mean headroom; 0.5 means the protocol is at twice the limit.
        """
        requested = self.charge_per_phase_uC
        return self.max_charge_uC / requested if requested > 0 else math.inf

    def describe(self) -> str:
        """Multi-line summary."""
        verdict = "PASS" if self.passes else "EXCEEDS"
        # The threshold as given and the metric on its side of it (ledger 163).
        threshold = format_setting(self.k_threshold)
        applied = format_against(
            self.k_metric, threshold, exceeds=not self.passes, decimals=3
        )
        return "\n".join(
            [
                f"Shannon k = {applied} vs threshold {threshold} -> {verdict}",
                f"  charge/phase    {self.charge_per_phase_uC:.4g} uC "
                f"(limit {format_limit(self.max_charge_uC)} uC)",
                f"  charge density  {self.charge_density_uC_cm2:.4g} uC/cm^2",
                f"  current limit   {format_limit(self.max_current_uA)} uA "
                f"({self.current_margin:.2f}x requested)",
            ]
        )


def max_current_interval_uA(
    area_cm2: float,
    pulse_width_us: float,
    k_bounds: tuple[float, float] = K_BOUNDS,
) -> Interval:
    """Current limit across the whole supported ``k`` band rather than at one ``k``.

    Merrill et al. give ``2.0 > k > 1.5`` without singling out a value, so the honest
    Shannon limit is the interval this returns. Because ``Q_max`` goes as
    ``sqrt(10^k)``, the 1.5-2.0 band is a factor of ``sqrt(10^0.5)`` = 1.78 in current.
    """
    from ..uncertainty import Interval

    low_k, high_k = k_bounds
    return Interval(
        shannon_max_current_uA(area_cm2, pulse_width_us, low_k),
        shannon_max_current_uA(area_cm2, pulse_width_us, high_k),
    )


def evaluate(
    charge_per_phase_uC: float,
    area_cm2: float,
    pulse_width_us: float,
    k: float = K_DEFAULT,
) -> ShannonResult:
    """Evaluate the full Shannon criterion and package the result."""
    return ShannonResult(
        k_metric=shannon_k(charge_per_phase_uC, area_cm2),
        k_threshold=k,
        charge_per_phase_uC=charge_per_phase_uC,
        charge_density_uC_cm2=charge_per_phase_uC / area_cm2,
        max_charge_uC=shannon_max_charge_uC(area_cm2, k),
        max_current_uA=shannon_max_current_uA(area_cm2, pulse_width_us, k),
        area_cm2=area_cm2,
    )
