"""Stimulation waveform description.

The prototype's four-field protocol (current, pulse width, frequency, train duration)
is preserved as the leading positional arguments, so
``StimProtocol(80, 200, 130, 1)`` still means what it did. Everything added after that
is optional and defaults to the most common laboratory case: a symmetric,
charge-balanced, cathodic-first biphasic pulse with no interphase gap.

Why the extra fields matter for safety rather than being decoration:

- **Charge balance** is the single strongest determinant of electrode corrosion and
  net faradaic product accumulation. A monophasic protocol is not made safe by
  satisfying the Shannon criterion.
- **Phase asymmetry** changes which electrode potential extreme is approached, and
  published charge-injection limits differ between anodic-first and cathodic-first
  pulsing by a factor of two for platinum (Rose & Robblee 1990).
- **Duty cycle** governs average power dissipation, which is what the thermal model
  integrates -- not the peak pulse current.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .units import charge_uC

Waveform = Literal["biphasic", "monophasic"]

DEFAULT_CHARGE_RECOVERY_RATIO = 1.0
"""An ideally balanced pulse: the return phase recovers every coulomb injected.

A named constant rather than a literal in the field declaration, because the GUI declares
the same default a second time and a drift between the two would give one set of inputs
two answers depending on how they were entered -- which is what happened to the Shannon
``k`` box (``tests/test_gui.py::TestDefaultsMatchTheLibrary``).
"""

DEFAULT_TRAIN_DUTY_CYCLE = 1.0
"""A continuous train: the schedule McCreery et al. (2010) ran their 100 % duty arm at.

Named for the same reason as :data:`DEFAULT_CHARGE_RECOVERY_RATIO`, and load bearing for a
second: at this value the train-duty excursion's fold is exactly 1.0 and the validated
envelope's inside-PASS branch stays reachable. A default that produced any other fold would
leave that branch dead in a new way (ledger 6, 67(a)).
"""

CHARGE_BALANCE_REL_TOLERANCE = 1e-12
"""Fraction of the phase charge that may go unrecovered and still count as balanced.

A float-rounding window, deliberately, and not a safety threshold: it exists so that a
protocol whose two phases are the same product in a different association reads as
balanced. The safety question -- whether a given imbalance matters -- is answered by the
DC-drift model on the water-window check, which has the electrode area, the interfacial
capacitance and the train duration that question needs. Twelve orders of magnitude is far
below any imbalance a driver produces and far above the handful of ulps an exact
cancellation can accumulate.
"""


@dataclass(frozen=True)
class StimProtocol:
    """A pulse train specification.

    Parameters
    ----------
    current_uA:
        Amplitude of the leading (stimulating) phase, in microamperes. Always given as
        a positive magnitude; ``anodic_first`` carries the polarity.
    pulse_width_us:
        Width of the leading phase, in microseconds.
    frequency_hz:
        Pulse repetition rate within a train.
    train_duration_s:
        Duration of one train. Use ``math.inf`` for continuous stimulation.
    waveform:
        ``"biphasic"`` (default) or ``"monophasic"``.
    interphase_gap_us:
        Open-circuit interval between the two phases of a biphasic pulse.
    anodic_first:
        Whether the leading phase is anodic. Default ``False`` (cathodic-first), which
        is the usual choice for neural excitation and the lower-dissolution polarity
        for platinum.
    return_phase_ratio:
        Width multiplier of the return phase relative to the leading phase. ``1.0`` is
        symmetric. A value of ``r`` gives a return phase of width ``W*r``, and -- at full
        charge recovery -- amplitude ``I/r``, which keeps the pulse charge-balanced while
        lowering the return-phase current density.
    charge_recovery_ratio:
        Fraction of the injected charge the return phase actually recovers. ``1.0``
        (default) is an ideally balanced pulse; ``0.9`` leaves a tenth of every phase
        charge at the interface as direct current; above ``1.0`` the return phase
        over-recovers and the residual reverses sign.

        This is the degree of freedom the prototype did not have, and its absence made
        imbalance structurally inexpressible: the return phase was derived as
        ``I/r`` over a width ``W*r``, whose product is ``I*W`` for every ``r``, so the
        return charge was identically the leading charge and ``net_charge_per_pulse_uC``
        was identically zero. 150 swept ``(I, W, r)`` combinations produced no imbalance,
        the charge-balance FAIL branch was dead code and ``net_dc_current_uA`` was a
        constant zero (ledger 3). A real driver's mismatched return phase, a blocking
        capacitor that has not settled, and a shorting phase cut short are all this one
        number.

        Named for the charge rather than the amplitude because the charge is what every
        consumer reads. Under this parameterisation the return phase carries
        ``I * r_a / r`` over ``W * r``, so a caller asking for
        ``return_phase_ratio=0.25, charge_recovery_ratio=0.9`` gets a quarter-width
        return phase at 3.6x the leading amplitude -- which is 90 % of the *charge*, and
        would have been a surprise under an "amplitude ratio" spelling (fix plan D6).
    train_duty_cycle:
        Fraction of wall-clock time the train is running, as an on/off schedule. ``1.0``
        (default) is continuous.

        **Not** :attr:`duty_cycle`, and the distinction is the whole of ledger 6. That one
        is the fraction of each *period* during which current flows -- a few per cent for
        any pulsed protocol -- and it is a property of the pulse. This one is the schedule
        McCreery et al. (2010) actually varied: one second on, one second off shrank the
        damage radius from at least 150 um to about 60 um at identical charge per phase and
        identical charge density. Comparing the first against the second is a category
        error, and it made the validated-envelope check's inside-PASS branch unreachable
        for every pulsed protocol -- McCreery's own fit protocol reported a duty fold of 25.

        Governs what a duty cycle is supposed to govern: the pulse count, the mean current
        and, through its square root, the RMS current the thermal model integrates. At the
        ``1.0`` default every one of those is unchanged.
    """

    current_uA: float
    pulse_width_us: float
    frequency_hz: float
    train_duration_s: float
    waveform: Waveform = "biphasic"
    interphase_gap_us: float = 0.0
    anodic_first: bool = False
    return_phase_ratio: float = 1.0
    charge_recovery_ratio: float = DEFAULT_CHARGE_RECOVERY_RATIO
    train_duty_cycle: float = DEFAULT_TRAIN_DUTY_CYCLE

    def __post_init__(self) -> None:
        for name in ("current_uA", "pulse_width_us", "frequency_hz"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and > 0, got {value!r}")
        if math.isnan(self.train_duration_s) or self.train_duration_s <= 0:
            raise ValueError(
                f"train_duration_s must be > 0 (or math.inf for continuous), "
                f"got {self.train_duration_s!r}"
            )
        if self.waveform not in ("biphasic", "monophasic"):
            raise ValueError(
                f"waveform must be 'biphasic' or 'monophasic', got {self.waveform!r}"
            )
        if not math.isfinite(self.interphase_gap_us) or self.interphase_gap_us < 0:
            raise ValueError(
                f"interphase_gap_us must be finite and >= 0, "
                f"got {self.interphase_gap_us!r}"
            )
        if not math.isfinite(self.return_phase_ratio) or self.return_phase_ratio <= 0:
            raise ValueError(
                f"return_phase_ratio must be finite and > 0, "
                f"got {self.return_phase_ratio!r}"
            )
        # Zero is admissible and means a return phase that recovers nothing -- a real
        # fault, and the one this field exists to let a user enter. Negative is not: the
        # polarity of the return phase is fixed by `anodic_first`, so a negative fraction
        # would describe a second leading phase while quietly reporting a net charge
        # larger than the one injected.
        if not math.isfinite(self.charge_recovery_ratio) or self.charge_recovery_ratio < 0:
            raise ValueError(
                f"charge_recovery_ratio must be finite and >= 0, "
                f"got {self.charge_recovery_ratio!r}"
            )
        if (
            not math.isfinite(self.train_duty_cycle)
            or not 0.0 < self.train_duty_cycle <= 1.0
        ):
            raise ValueError(
                f"train_duty_cycle must be finite and in (0, 1], "
                f"got {self.train_duty_cycle!r}"
            )
        if self.active_duration_us > self.period_us:
            raise ValueError(
                f"Pulse does not fit in its period: active duration "
                f"{self.active_duration_us:g} us exceeds the "
                f"{self.period_us:g} us period at {self.frequency_hz:g} Hz"
            )

    # --- timing ---------------------------------------------------------------

    @property
    def period_us(self) -> float:
        """Inter-pulse period in microseconds."""
        return 1e6 / self.frequency_hz

    @property
    def return_phase_width_us(self) -> float:
        """Width of the return phase; zero for a monophasic pulse."""
        if self.waveform == "monophasic":
            return 0.0
        return self.pulse_width_us * self.return_phase_ratio

    @property
    def return_phase_current_uA(self) -> float:
        """Amplitude of the return phase; zero for a monophasic pulse.

        ``I * r_a / r``: the width ratio ``r`` sets how long the return phase lasts and
        the recovery ratio ``r_a`` how much charge it moves, so the amplitude is what the
        two together require. With ``r_a = 1`` this is the prototype's ``I / r`` exactly,
        bit for bit.
        """
        return self.return_phase_current_at_uA(self.current_uA)

    def return_phase_current_at_uA(self, current_uA: float) -> float:
        """The return-phase amplitude this waveform carries at a given leading amplitude.

        The waveform's shape is fixed by the two ratios; only its scale is the amplitude.
        Written as a method because two back-solves need it at amplitudes other than the
        one configured -- the current-density and compliance ceilings both have to ask
        "what does the return phase do if the leading phase is turned down to here?" --
        and a second copy of the expression is a second place for the two to disagree.

        Left-to-right, exactly as the prototype's ``current_uA / return_phase_ratio`` was:
        at the ``1.0`` recovery default ``(I * 1.0) / r`` is bit-identical to ``I / r``,
        while ``I * (1.0 / r)`` is not for a ratio like 3.
        """
        if self.waveform == "monophasic":
            return 0.0
        return current_uA * self.charge_recovery_ratio / self.return_phase_ratio

    @property
    def active_duration_us(self) -> float:
        """Total time per pulse spent delivering current, including the gap."""
        if self.waveform == "monophasic":
            return self.pulse_width_us
        return self.pulse_width_us + self.interphase_gap_us + self.return_phase_width_us

    @property
    def duty_cycle(self) -> float:
        """Fraction of time current is flowing, ignoring the interphase gap."""
        current_time = self.pulse_width_us + self.return_phase_width_us
        return current_time / self.period_us

    @property
    def n_pulses(self) -> float:
        """Number of pulses delivered in one train; ``inf`` for continuous stimulation.

        Scaled by :attr:`train_duty_cycle`: a train that runs half the wall-clock time
        delivers half the pulses over the same span, and total pulse count is a reported
        damage factor.
        """
        if math.isinf(self.train_duration_s):
            return math.inf
        return self.train_duration_s * self.frequency_hz * self.train_duty_cycle

    # --- charge ---------------------------------------------------------------

    @property
    def charge_per_phase_uC(self) -> float:
        """Charge delivered by the leading phase, in microcoulombs.

        This is the quantity ``Q`` in the Shannon criterion and in every published
        charge-injection limit. It is *not* the charge per pulse.
        """
        return charge_uC(self.current_uA, self.pulse_width_us)

    @property
    def return_charge_uC(self) -> float:
        """Charge recovered by the return phase, in microcoulombs."""
        return charge_uC(self.return_phase_current_uA, self.return_phase_width_us)

    @property
    def net_charge_per_pulse_uC(self) -> float:
        """Leading-phase charge minus recovered charge.

        Zero for an ideal charge-balanced biphasic pulse; equal to the full phase
        charge for a monophasic pulse. Any non-zero value accumulates over the train.

        Signed: positive when the leading phase dominates, negative when the return phase
        over-recovers. The sign is the direction the interface drifts, which the
        water-window check needs in order to know which edge it is heading for.
        """
        return self.net_charge_at_uA(self.current_uA)

    def net_charge_at_uA(self, current_uA: float) -> float:
        """Unrecovered charge per pulse at a given leading amplitude.

        The companion to :meth:`return_phase_current_at_uA`, and there for the same
        reason: the water-window drift ceiling is back-solved over amplitude, so the
        predicate has to ask what this waveform leaves behind at an amplitude the
        protocol was never configured at. One expression, so the reported DC and the
        one the ceiling inverts cannot drift apart.
        """
        return charge_uC(current_uA, self.pulse_width_us) - charge_uC(
            self.return_phase_current_at_uA(current_uA), self.return_phase_width_us
        )

    def net_dc_current_at_uA(self, current_uA: float) -> float:
        """Time-averaged unrecovered current at a given leading amplitude."""
        return self.net_charge_at_uA(current_uA) * self.frequency_hz

    @property
    def is_charge_balanced(self) -> bool:
        """Whether the pulse recovers all injected charge, to within rounding.

        Relative to :attr:`charge_per_phase_uC`, not an absolute microcoulomb window
        (ledger 15). The absolute form was benign only because the field that makes
        imbalance expressible did not exist: at 1 A and 1 ms the phase charge is 1000 uC
        and one ulp of it is 2.3e-13 uC, so a handful of roundings in a *symmetric*
        protocol crosses an absolute 1e-12 uC threshold and the pulse is reported
        unbalanced; at nanoampere amplitudes the same window hides an imbalance of order
        one. The quantity that matters is the fraction of the injected charge left
        behind, so that is what the tolerance is expressed in.
        """
        return abs(self.net_charge_per_pulse_uC) <= (
            CHARGE_BALANCE_REL_TOLERANCE * self.charge_per_phase_uC
        )

    @property
    def net_dc_current_uA(self) -> float:
        """Time-averaged net (unrecovered) current over the train, in microamperes.

        A non-zero value is a direct-current offset. Sustained DC at an electrode
        drives irreversible faradaic reactions regardless of how favourable the
        per-pulse charge density looks.
        """
        return self.net_dc_current_at_uA(self.current_uA)

    @property
    def total_charge_per_train_uC(self) -> float:
        """Summed leading-phase charge over one train; ``inf`` if continuous."""
        return self.charge_per_phase_uC * self.n_pulses

    @property
    def average_current_uA(self) -> float:
        """Root-mean-square-free time-average of the absolute current.

        Used by the thermal model, which responds to average dissipated power rather
        than to peak pulse amplitude.
        """
        charge_moved = self.charge_per_phase_uC + self.return_charge_uC
        return charge_moved * self.frequency_hz * self.train_duty_cycle

    @property
    def rms_current_uA(self) -> float:
        """RMS current of the rectangular pulse train.

        Joule heating scales with the square of current, so this -- not the average --
        is what drives ohmic power dissipation.
        """
        lead = self.current_uA**2 * self.pulse_width_us
        ret = self.return_phase_current_uA**2 * self.return_phase_width_us
        # The off part of the train contributes no current and therefore no heating, so
        # the mean square is scaled by the duty and the RMS by its square root.
        return math.sqrt((lead + ret) * self.train_duty_cycle / self.period_us)

    @property
    def leading_polarity(self) -> str:
        """``'anodic'`` or ``'cathodic'`` for the leading phase."""
        return "anodic" if self.anodic_first else "cathodic"

    def describe(self) -> str:
        """Multi-line human-readable summary."""
        train = (
            "continuous"
            if math.isinf(self.train_duration_s)
            else f"{self.train_duration_s:g} s ({self.n_pulses:.0f} pulses)"
        )
        lines = [
            f"{self.waveform} {self.leading_polarity}-first, "
            f"{self.current_uA:g} uA x {self.pulse_width_us:g} us @ "
            f"{self.frequency_hz:g} Hz, train {train}",
            f"  charge/phase:   {self.charge_per_phase_uC:.4g} uC",
            f"  duty cycle:     {self.duty_cycle * 100:.2f} % (within each period)",
            f"  RMS current:    {self.rms_current_uA:.4g} uA",
        ]
        if self.interphase_gap_us:
            lines.append(f"  interphase gap: {self.interphase_gap_us:g} us")
        if self.return_phase_ratio != 1.0 and self.waveform == "biphasic":
            lines.append(
                f"  return phase:   {self.return_phase_current_uA:.4g} uA x "
                f"{self.return_phase_width_us:g} us "
                f"(ratio {self.return_phase_ratio:g})"
            )
        if self.train_duty_cycle != DEFAULT_TRAIN_DUTY_CYCLE:
            lines.append(
                f"  train duty:     {self.train_duty_cycle * 100:.1f} % of wall-clock "
                f"time (on/off schedule)"
            )
        if self.charge_recovery_ratio != 1.0 and self.waveform == "biphasic":
            lines.append(
                f"  charge recovery: {self.charge_recovery_ratio * 100:.1f} % of the "
                f"injected charge is returned"
            )
        if not self.is_charge_balanced:
            lines.append(
                f"  NET CHARGE:     {self.net_charge_per_pulse_uC:.4g} uC/pulse "
                f"-> {self.net_dc_current_uA:.4g} uA DC"
            )
        return "\n".join(lines)
