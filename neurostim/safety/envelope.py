"""How far a protocol sits outside the conditions its damage criterion was fitted to.

The problem
-----------
The Shannon criterion is a fit to one experiment: McCreery et al. (1990), 400 us per
phase, 50 Hz, 7 h continuous, cat parietal cortex, platinum surface discs of
0.01-0.5 cm^2. Shannon says plainly that extrapolation is not established:

    "At the present time we do not adequately know how to extrapolate from this data to
    predict damage thresholds for longer stimulation durations, or for higher
    stimulation rates, or even for different pulse durations."

Clinical DBS runs at 130-185 Hz, essentially continuously, for years. That is two to
four times the frequency and four orders of magnitude the duration of the underlying
data. A criterion evaluated there is being asked a question its evidence cannot answer,
and reporting a comfortable PASS would misrepresent that.

Excursions are not symmetric
----------------------------
Departing the envelope is not equally worrying in both directions:

- **Frequency above 50 Hz is non-conservative.** A frequency-dependent damage threshold
  has been reported (Agnew et al. 1983, via Kuncel & Grill 2004), and Cogan et al.
  (2016) summarise McCreery et al. (1995, 1997) as showing that "lower frequency
  stimulation invariably resulted in reduced nerve damage and reduced SIDNE". Below
  50 Hz is therefore the safe direction.
- **Duration beyond 7 h is non-conservative** for the same reason: more total pulses.
- **Pulse width in either direction is simply unknown.** Shannon lists it explicitly
  among the extrapolations he cannot support, and Cogan et al. (2016) go further --
  for microelectrodes the charge-density/charge-per-phase codependence does not hold
  at all.

What this module does
---------------------
It does not invent a derating factor; no source in this package's bibliography supports
one. It quantifies the excursion, labels its direction, and lets the assessment refuse
to report an unqualified PASS outside the envelope. Turning "we are 2.6x outside the
data" into a number is the honest available action.

Why there is no pulse-duty excursion
------------------------------------
There used to be one, comparing the protocol's *intra-pulse* current-flowing fraction --
a few per cent for anything pulsed -- against McCreery et al. (2010)'s **train** on/off
schedule. Those are different quantities, and the comparison made the inside-PASS branch
below unreachable for every pulsed protocol: McCreery's own fit conditions, 400 us at
50 Hz for 7 h, reported a duty fold of 25 and ``inside = False`` (ledger 6, 67(a)).

It is deleted rather than rescaled, and the reason is arithmetic rather than taste. For a
symmetric biphasic pulse ``duty = 2 * PW * f * 1e-6``, so ``duty_fold`` is *identically*
``pw_fold * freq_fold`` -- the product of two excursions already reported above, each with
its own sourced direction. Verified: 100 us at 200 Hz is fourfold outside on both real axes
and gives a duty fold of exactly 1.000, while 600 us at 75 Hz is inside on both and gives
2.250, which would have manufactured a Shannon CAUTION from two parameters no source here
objects to. No source in this bibliography gives the pulse duty an independent basis.

What replaces it is ``StimProtocol.train_duty_cycle`` and the excursion below, which is the
comparison McCreery's experiment actually supports. At its default of 1.0 -- a continuous
train, which is what McCreery's 100 % duty arm ran -- the fold is exactly 1.0, so
``inside`` stays reachable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from ..data import mccreery1995, mccreery2010
from ..protocol import StimProtocol

Direction = Literal["inside", "conservative", "non_conservative", "unknown"]

# --- the envelope of the McCreery data behind the Shannon fit ---------------------

PULSE_WIDTH_US = 400.0
FREQUENCY_HZ = 50.0
DURATION_H = 7.0
AREA_RANGE_CM2 = (0.01, 0.5)
PREPARATION = "cat parietal cortex, platinum surface discs"
WAVEFORM = "anodic-first, charge-balanced, symmetric biphasic"

TOLERANCE_FOLD = 2.0
"""Fold departure tolerated before a parameter counts as outside the envelope."""


@dataclass(frozen=True)
class Excursion:
    """How far one parameter departs from the value the criterion was fitted at."""

    parameter: str
    value: float
    reference: float
    units: str
    direction: Direction
    rationale: str = ""

    @property
    def fold(self) -> float:
        """Fold difference from the reference, always >= 1."""
        if self.reference == 0 or self.value == 0:
            return math.inf
        return max(self.value / self.reference, self.reference / self.value)

    @property
    def outside(self) -> bool:
        """Whether the departure exceeds :data:`TOLERANCE_FOLD`."""
        return self.direction != "inside" and self.fold > TOLERANCE_FOLD

    @property
    def concerning(self) -> bool:
        """Whether the excursion is in a direction that reduces safety margin."""
        return self.outside and self.direction in ("non_conservative", "unknown")

    def describe(self) -> str:
        """One-line rendering."""
        if not self.outside:
            return (
                f"{self.parameter}: {self.value:g} {self.units} "
                f"(reference {self.reference:g}, within {TOLERANCE_FOLD:g}x)"
            )
        label = {
            "conservative": "safer direction",
            "non_conservative": "REDUCES MARGIN",
            "unknown": "direction of effect unknown",
        }[self.direction]
        value = "continuous" if math.isinf(self.value) else f"{self.value:g} {self.units}"
        distance = (
            "unbounded against"
            if math.isinf(self.fold)
            else f"{self.fold:.1f}x from"
        )
        text = (
            f"{self.parameter}: {value} is {distance} "
            f"the {self.reference:g} {self.units} of the underlying data -- {label}"
        )
        if self.rationale:
            text += f". {self.rationale}"
        return text


@dataclass(frozen=True)
class EnvelopeResult:
    """Every parameter excursion for one protocol and electrode."""

    excursions: tuple[Excursion, ...]
    area_cm2: float | None = None
    area_in_range: bool = True

    @property
    def outside(self) -> tuple[Excursion, ...]:
        """Excursions beyond tolerance, in any direction."""
        return tuple(e for e in self.excursions if e.outside)

    @property
    def concerning(self) -> tuple[Excursion, ...]:
        """Excursions that reduce the safety margin or whose effect is unknown."""
        return tuple(e for e in self.excursions if e.concerning)

    @property
    def inside(self) -> bool:
        """Whether the protocol sits wholly within the validated envelope."""
        return not self.outside and self.area_in_range

    @property
    def supports_unqualified_pass(self) -> bool:
        """Whether a PASS from the Shannon criterion can be taken at face value.

        False as soon as any parameter departs in a non-conservative or unknown
        direction, or the electrode area is outside the range the fit covers.
        """
        return not self.concerning and self.area_in_range

    def describe(self) -> str:
        """Multi-line summary."""
        lines = [
            "Validated envelope of the Shannon fit "
            f"({PULSE_WIDTH_US:g} us, {FREQUENCY_HZ:g} Hz, {DURATION_H:g} h, "
            f"{PREPARATION})"
        ]
        for excursion in self.excursions:
            marker = "  !" if excursion.concerning else "   "
            lines.append(f"{marker} {excursion.describe()}")
        if self.area_cm2 is not None and not self.area_in_range:
            lines.append(
                f"  ! electrode area {self.area_cm2:.3g} cm^2 is outside the "
                f"{AREA_RANGE_CM2[0]:g}-{AREA_RANGE_CM2[1]:g} cm^2 range of the "
                f"platinum discs the fit was derived from"
            )
        if not self.supports_unqualified_pass:
            lines.append(
                "  -> a PASS from the Shannon criterion cannot be taken at face value "
                "here;\n     no derating factor is applied because no source in this "
                "bibliography supports one"
            )
        return "\n".join(lines)


def evaluate(protocol: StimProtocol, area_cm2: float | None = None) -> EnvelopeResult:
    """Compare a protocol against the conditions the Shannon fit was derived under."""
    excursions: list[Excursion] = []

    pw_fold = max(
        protocol.pulse_width_us / PULSE_WIDTH_US,
        PULSE_WIDTH_US / protocol.pulse_width_us,
    )
    excursions.append(
        Excursion(
            parameter="pulse width",
            value=protocol.pulse_width_us,
            reference=PULSE_WIDTH_US,
            units="us",
            direction="unknown" if pw_fold > TOLERANCE_FOLD else "inside",
            rationale=(
                "Shannon lists pulse duration among the extrapolations he cannot support"
                if pw_fold > TOLERANCE_FOLD
                else ""
            ),
        )
    )

    if protocol.frequency_hz > FREQUENCY_HZ:
        freq_direction: Direction = "non_conservative"
        freq_rationale = mccreery1995.describe_frequency_risk(protocol.frequency_hz)
    else:
        freq_direction = "conservative"
        freq_rationale = mccreery1995.describe_frequency_risk(protocol.frequency_hz)
    excursions.append(
        Excursion(
            parameter="frequency",
            value=protocol.frequency_hz,
            reference=FREQUENCY_HZ,
            units="Hz",
            direction=freq_direction,
            rationale=freq_rationale,
        )
    )

    if math.isinf(protocol.train_duration_s):
        excursions.append(
            Excursion(
                parameter="duration",
                value=math.inf,
                reference=DURATION_H,
                units="h",
                direction="non_conservative",
                rationale=(
                    "continuous stimulation is unbounded against a 7 h experiment; "
                    "total pulse count is a reported damage factor"
                ),
            )
        )
    else:
        hours = protocol.train_duration_s / 3600.0
        direction: Direction = (
            "non_conservative" if hours > DURATION_H else "conservative"
        )
        excursions.append(
            Excursion(
                parameter="duration",
                value=hours,
                reference=DURATION_H,
                units="h",
                direction=direction,
                rationale=(
                    "total pulse count is a reported damage factor"
                    if direction == "non_conservative"
                    else "shorter exposure than the underlying experiment"
                ),
            )
        )

    # The TRAIN schedule, not the intra-pulse current-flowing fraction. See the module
    # docstring: the two are different quantities and only this one is what McCreery
    # et al. (2010) varied.
    excursions.append(
        Excursion(
            parameter="train duty cycle",
            value=protocol.train_duty_cycle * 100.0,
            reference=100.0,
            units="%",
            direction=(
                "conservative" if protocol.train_duty_cycle < 0.95 else "inside"
            ),
            rationale=mccreery2010.duty_cycle_note(protocol.train_duty_cycle),
        )
    )

    in_range = True
    if area_cm2 is not None:
        in_range = AREA_RANGE_CM2[0] <= area_cm2 <= AREA_RANGE_CM2[1]

    return EnvelopeResult(
        excursions=tuple(excursions),
        area_cm2=area_cm2,
        area_in_range=in_range,
    )
