"""Water-window polarisation check.

The water window is the potential range between the reduction of water to hydrogen
(cathodic limit) and its oxidation to oxygen (anodic limit). Merrill et al. (2005):
once the electrode potential reaches either boundary, *all* further injected charge
goes into irreversible water electrolysis, because water is not mass-transport limited
in an aqueous medium.

Model used here
---------------
The interface is treated as a capacitance, so injecting a charge density produces

.. math::

    \\Delta V = \\frac{Q/A}{C_{eff}}

The question is what ``C_eff`` should be, and getting it wrong makes this check useless.

**Why the double-layer value alone is not usable.** Merrill et al.'s footnote 2 gives a
smooth-metal double-layer capacitance of 20 uF/cm^2. Using it for platinum predicts the
water window is reached at about 12 uC/cm^2 -- while Rose & Robblee *measured* that
platinum stays inside the window up to 100-150 uC/cm^2. That is a tenfold internal
contradiction between two numbers this package already holds, and it fired a false alarm
on essentially every realistic protocol.

The discrepancy is physical, not a bug: platinum and iridium oxide are pseudocapacitive.
Much of the injected charge goes into reversible surface reactions rather than charging
the double layer. Merrill quotes platinum's pseudocapacitance as 210 uC/cm^2 of real
area (Rand & Woods 1971), an order of magnitude above double-layer storage.

**What is done instead.** ``C_eff`` is derived from the material's own measured
charge-injection limit and window, so that injecting exactly the CIC brings the electrode
exactly to the window edge -- which is what the CIC *means*. The two numbers are then
consistent by construction rather than contradictory.

**What that leaves this check doing.** Not an independent test of charge density: the
charge-injection check already covers that, from the same measurement. What it adds is
the effect of anything that shifts the starting potential -- a non-zero resting
potential, or the interpulse bias several materials require to reach their quoted limit.
Those genuinely move the excursion and are not captured anywhere else. Supplying a
measured ``capacitance_uF_cm2`` overrides the derivation entirely.

**And what the train leaves behind** (ledger 2, C2.3). Every per-pulse limit here was
measured or derived on a charge-balanced waveform. A waveform that recovers less than it
injects charges the same capacitor a little more with every pulse, and :class:`DcDrift`
asks when that offset, together with the part of each pulse that rides on top of it
(ledger 105), reaches the window edge. Reaching it before the train ends is a FAIL, and
afterwards a CAUTION, so an unbalanced waveform never gets a bare PASS. The capacitor has
no leakage, so the time is a lower bound. A continuous train with any unrecovered charge
therefore permits no current at all, which is a bound from the model, not a sourced
threshold (ledger 118). Inside ``SafetyCalculator.assess`` the clause runs only when
Charge balance calls the waveform unbalanced, so the two checks read one test.

The ohmic ``I * R_access`` drop across the tissue is *not* part of the electrode
potential and is excluded here; it belongs to the compliance-voltage calculation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..materials import Material, WaterWindow, get_material

DOUBLE_LAYER_CAPACITANCE_uF_cm2 = 20.0
"""Canonical smooth-metal double-layer capacitance (Merrill et al. 2005, footnote 2)."""


def effective_capacitance_uF_cm2(
    material: Material | str, *, anodic_first: bool | None = None
) -> float:
    """Interfacial capacitance implied by a material's own CIC and water window.

    Defined so that injecting the charge-injection limit brings the electrode exactly to
    the window edge, which is the definition of that limit. Falls back to the
    double-layer value when the material has no window on record.

    For platinum this returns 250 uF/cm^2 rather than 20, an order of magnitude above
    double-layer storage and consistent with its known pseudocapacitance.
    """
    mat = material if isinstance(material, Material) else get_material(material)
    if mat.water_window is None:
        return DOUBLE_LAYER_CAPACITANCE_uF_cm2
    # The CIC is the charge that just reaches the window edge, so the widest measured
    # value defines the excursion per coulomb.
    limit = mat.cic_uC_cm2("optimistic", anodic_first)
    # Use the half-window the leading phase actually swings toward. An anodic-first
    # pulse drives the electrode positive and is bounded by the anodic limit; a
    # cathodic-first pulse by the cathodic one. Windows are not symmetric, so this
    # matters. With polarity unknown, take the narrower half.
    if anodic_first is True:
        available_V = abs(mat.water_window.anodic_V)
    elif anodic_first is False:
        available_V = abs(mat.water_window.cathodic_V)
    else:
        available_V = min(
            abs(mat.water_window.cathodic_V), abs(mat.water_window.anodic_V)
        )
    if available_V <= 0:  # pragma: no cover - windows always straddle zero here
        return DOUBLE_LAYER_CAPACITANCE_uF_cm2
    return limit / available_V


def validate_resting_potential_V(
    material: Material | str, resting_potential_V: float
) -> None:
    """Raise unless the electrode is inside its own window before any current flows.

    Two things go wrong when it is not, and the second is the reason this is a rejection
    rather than a caveat.

    The visible one is that the answers stop meaning anything:
    ``max_charge_density_in_window_uC_cm2("Pt", resting_potential_V=5.0)`` used to report
    1400 uC/cm^2 "allowed" for an interface already 4.2 V past its anodic limit at rest
    (ledger 14). The negative direction was caught only incidentally, by the
    ``available_V <= 0`` guard.

    The structural one is that the water-window verdict stops being monotone in current.
    From outside the anodic limit a small cathodic pulse pulls the interface back INTO the
    window while a large one breaches it on the other side, so the check reads FAIL, PASS,
    FAIL as amplitude rises. Every reported limit in this package is produced by
    "the largest value that still passes", which is the wrong question for a predicate
    with two boundaries -- and it is the precondition ``_limits.floor_to_pass`` declares
    and asserts. Phase 0b measured the scope: over 1824 swept configurations *every*
    non-monotone case was an out-of-window resting potential, and across 630 in-window
    configurations there were none. Rejecting the input makes the precondition true rather
    than merely asserted.

    A material with no window on record is not validated: there is nothing to be outside
    of, and the check reports NOT_EVALUATED.

    Inclusive at both ends, matching :meth:`WaterWindow.contains`, so the rejection cannot
    disagree with the check it protects about the boundary itself.
    """
    if not math.isfinite(resting_potential_V):
        raise ValueError(
            f"resting_potential_V must be finite, got {resting_potential_V!r}"
        )
    mat = material if isinstance(material, Material) else get_material(material)
    window = mat.water_window
    if window is None or window.contains(resting_potential_V):
        return
    raise ValueError(
        f"resting_potential_V = {resting_potential_V:g} V is outside {mat.key}'s water "
        f"window [{window.cathodic_V:g}, {window.anodic_V:g}] V ({window.scale}). "
        f"An electrode already outside its window at rest is in irreversible "
        f"electrolysis before the pulse begins, so no charge-injection limit computed "
        f"here applies to it; and the water-window verdict is then non-monotone in "
        f"current, which every reported limit in this package assumes it is not. "
        f"Supply the electrode's measured open-circuit potential on the window's own "
        f"scale."
    )


def polarisation_V(
    charge_density_uC_cm2: float,
    capacitance_uF_cm2: float = DOUBLE_LAYER_CAPACITANCE_uF_cm2,
) -> float:
    """Potential excursion from charging a double layer, in volts.

    ``uC/cm^2`` divided by ``uF/cm^2`` gives volts directly.
    """
    if not math.isfinite(capacitance_uF_cm2) or capacitance_uF_cm2 <= 0:
        raise ValueError(
            f"capacitance_uF_cm2 must be finite and > 0, got {capacitance_uF_cm2!r}"
        )
    return charge_density_uC_cm2 / capacitance_uF_cm2


def drift_headroom_V(
    window: WaterWindow, resting_potential_V: float, *, anodic: bool
) -> float:
    """Volts between rest and the window edge the net DC is heading for.

    The direction is the *net* charge's, not the leading phase's: a return phase that
    over-recovers leaves an offset of the opposite sign to the pulse that produced it.
    Non-negative whenever the resting potential is inside the window, which
    :func:`validate_resting_potential_V` guarantees at construction.
    """
    if anodic:
        return window.anodic_V - resting_potential_V
    return resting_potential_V - window.cathodic_V


def window_charge_uC(
    headroom_V: float, capacitance_uF_cm2: float, area_cm2: float
) -> float:
    """Charge that carries the interface from rest to the window edge.

    ``V * uF/cm^2 * cm^2 = uC`` directly. This is the budget a net DC current spends:
    the same capacitive model the peak excursion uses, integrated over the train instead
    of over one pulse.
    """
    return headroom_V * capacitance_uF_cm2 * area_cm2


@dataclass(frozen=True)
class DcDrift:
    """How long an unrecovered current takes to reach the window edge.

    The failure mode every per-pulse limit in this package misses. Charge-injection
    limits, the Shannon criterion and the peak excursion are all measured or derived on a
    charge-balanced waveform, so each describes what one pulse does and none describes
    what a thousand of them leave behind. On the audit's case -- a clinical band at
    3000 uA, 90 us, 130 Hz, monophasic -- the peak excursion is 0.018 V into a 0.6 V
    window and the package reported PASS with 0.58 V of headroom, while the interface
    actually leaves the window in about a quarter of a second (ledger 2).

    The model is the interface as a capacitor charged by the mean unrecovered current:
    ``t = (Q_window - Q_riding) / I_dc`` with ``Q_window = dV * C * A``. Verified against
    pulse-by-pulse loops that follow both phases of every pulse, which reproduce it to
    within one pulse -- the finest time a pulse train can resolve.

    **The pulse rides on the offset** (ledger 105). After ``n`` pulses the offset is ``n``
    times the unrecovered charge, and pulse ``n``'s leading phase peaks at that offset
    plus the part of its own charge the return phase is about to recover:
    ``offset(n-1) + e = offset(n) + r_a * e``. So the offset has ``Q_window - r_a * Q``
    to spend, not ``Q_window``. For monophasic delivery ``r_a = 0``: each pulse is all
    offset and nothing rides, which is why the monophasic oracle could not see this. For a
    partial recovery the clause spent the whole budget on the offset and was
    anti-conservative: CAUTION "reaches the edge in 2.4 s, after the 1 s train" for an
    interface the same model takes out of the window at 0.42 s. An over-recovering pulse
    drifts toward the *other* edge, and its leading phase moves away from that edge, so
    nothing rides and the budget is the whole headroom.

    **At the branch it is stored on** (ledger 141). ``C`` is the ``C_eff`` of the polarity
    the offset heads for: the leading one for under-recovery, the opposite one for
    over-recovery. The window budget used the leading polarity's for both, so a
    cathodic-first Pt pulse drifting anodic was given 250 uF/cm^2 where the anodic branch
    holds 125, and twice the time to the edge. A measured ``capacitance_uF_cm2`` is one
    value and applies to both.
    """

    net_dc_current_uA: float
    """Signed mean unrecovered current; the sign is the direction of travel."""

    window_headroom_V: float
    """Volts from rest to the edge this offset is heading for."""

    window_charge_uC: float
    """``dV * C * A``: the charge budget before the edge is reached."""

    train_duration_s: float
    """How long the offset is applied for. ``inf`` for continuous stimulation."""

    riding_charge_uC: float = 0.0
    """Charge per pulse that peaks on top of the offset before the return phase recovers it.

    ``r_a * Q`` when the offset heads for the leading phase's edge, ``0.0`` when it heads
    for the other one or the pulse is monophasic. Spent from :attr:`window_charge_uC`
    before the offset gets any of it.
    """

    @property
    def drifts(self) -> bool:
        """Whether there is an offset to accumulate at all."""
        return self.net_dc_current_uA != 0.0

    @property
    def time_to_exit_s(self) -> float:
        """Seconds until the interface reaches the window edge; ``inf`` if never.

        ``(window - riding) / |I_dc|``: the offset's share of the budget over the rate it
        is spent. ``window`` is a constant and ``riding`` grows with amplitude, so the
        numerator falls and the denominator rises with current, and the time is monotone
        in floats as well as in exact arithmetic. Floored at zero: a pulse whose riding
        charge alone fills the window has already failed the peak clause.
        """
        if not self.drifts:
            return math.inf
        budget = max(self.window_charge_uC - self.riding_charge_uC, 0.0)
        return budget / abs(self.net_dc_current_uA)

    @property
    def exits_during_train(self) -> bool:
        """Whether the edge is reached before the train ends.

        Strict, so a train that ends exactly as the edge is reached is not a failure. A
        continuous train (``train_duration_s = inf``) reaches it for any non-zero offset,
        which is why the drift ceiling for one is ``0.0``.
        """
        return self.time_to_exit_s < self.train_duration_s

    def describe(self) -> str:
        """One or two lines on the offset and what it costs."""
        if not self.drifts:
            return "  DC drift      none: the waveform recovers its charge"
        if math.isinf(self.train_duration_s):
            # A continuous train, said in words rather than "(inf s)" (ledger 143).
            exit_note = "during continuous stimulation"
        else:
            exit_note = (
                "before the train ends"
                if self.exits_during_train
                else "after the train ends"
            ) + f" ({self.train_duration_s:g} s)"
        return (
            f"  DC drift      {self.net_dc_current_uA:+.4g} uA net DC against a "
            f"{self.window_charge_uC:.4g} uC window budget\n"
            f"                reaches the window edge in {self.time_to_exit_s:.4g} s, "
            f"{exit_note}"
        )


@dataclass(frozen=True)
class WaterWindowResult:
    """Outcome of the water-window check for one phase of a pulse."""

    material_key: str
    window: WaterWindow | None
    resting_potential_V: float
    excursion_V: float
    peak_potential_V: float
    polarity: str
    capacitance_uF_cm2: float
    interface_model: str = "capacitance derived from the material's own CIC and window"
    drift: DcDrift | None = None
    """The DC-drift budget, when a window is on record. ``None`` when none is.

    Carried on this result rather than on Charge balance, and the placement is the whole
    of fix plan D6. Charge balance bears no ceiling and its verdict must stay
    amplitude-independent -- that invariant is what licenses
    ``SafetyAssessment.unsafe_at_any_amplitude`` to read a FAIL there as "no amplitude is
    safe". Drift is not amplitude-independent: halve the amplitude and the time to the
    edge doubles. It belongs on the check that can express a ceiling.
    """

    @property
    def evaluated(self) -> bool:
        """Whether a water window was available for this material at all."""
        return self.window is not None

    @property
    def passes(self) -> bool:
        """Whether the peak potential stayed inside the window.

        Returns ``True`` when no window is on record -- the check did not fail, it did
        not run. Read :attr:`evaluated` alongside this.
        """
        if self.window is None:
            return True
        return self.window.contains(self.peak_potential_V)

    @property
    def headroom_V(self) -> float:
        """Volts remaining before the relevant window boundary is reached."""
        if self.window is None:
            return math.inf
        if self.polarity == "anodic":
            return self.window.anodic_V - self.peak_potential_V
        return self.peak_potential_V - self.window.cathodic_V

    def describe(self) -> str:
        """Multi-line summary."""
        if self.window is None:
            return (
                f"Water window ({self.material_key}) -> NOT EVALUATED\n"
                f"  no potential limits on record for this material in the cited source"
            )
        verdict = "PASS" if self.passes else "EXCEEDS"
        drift = self.drift
        if drift is not None and drift.drifts:
            # The verdict is both clauses, not the peak alone. A drift FAIL used to print
            # "-> PASS" above the peak headroom, the ledger-2 text under a FAIL (ledger 108).
            peak = "peak within window" if self.passes else "peak EXCEEDS"
            if drift.exits_during_train:
                verdict = f"EXCEEDS ({peak}; drift reaches the edge within the train)"
            else:
                # The check is a CAUTION here, never a PASS: the no-leak capacitor makes the
                # time a lower bound, not a licence (ledger 132).
                outcome = "CAUTION" if self.passes else "EXCEEDS"
                verdict = f"{outcome} ({peak}; drift reaches the edge after the train)"
        lines = [
            f"Water window ({self.material_key}, {self.polarity} phase) -> {verdict}",
            f"  window        {self.window.describe()}",
            f"  rest -> peak  {self.resting_potential_V:+.3f} V -> "
            f"{self.peak_potential_V:+.3f} V "
            f"(excursion {self.excursion_V:.3f} V)",
            f"  {'peak headroom' if drift is not None and drift.drifts else 'headroom':<13}"
            f" {self.headroom_V:+.3f} V",
            f"  interface     {self.interface_model}, "
            f"C_dl = {self.capacitance_uF_cm2:g} uF/cm^2",
        ]
        if self.drift is not None and self.drift.drifts:
            lines.append(self.drift.describe())
        return "\n".join(lines)


def evaluate(
    material: Material | str,
    charge_density_uC_cm2: float,
    *,
    anodic_first: bool = False,
    resting_potential_V: float = 0.0,
    capacitance_uF_cm2: float | None = None,
    anodic_first_for_capacitance: bool | None = None,
    net_dc_current_uA: float | None = None,
    area_cm2: float | None = None,
    train_duration_s: float | None = None,
    recovered_charge_uC: float = 0.0,
) -> WaterWindowResult:
    """Check whether the leading phase drives the electrode out of the water window.

    Parameters
    ----------
    resting_potential_V:
        Open-circuit electrode potential versus Ag|AgCl before the pulse. Defaults to
        0 V, which sits near the middle of the Pt/IrOx window. A real electrode's
        resting potential depends on its history and on any applied interpulse bias --
        several materials in the database reach their quoted charge-injection limit
        *only* under a positive bias, which this parameter is how you represent.

        Must lie inside the material's own window; a value outside it raises
        ``ValueError``. See :func:`validate_resting_potential_V`.
    recovered_charge_uC:
        Charge per pulse the return phase recovers, ``r_a * Q``; ``0.0`` for a monophasic
        pulse. When the offset heads for the leading phase's edge this part of each pulse
        peaks on top of it, so the drift budget spends it first (ledger 105). Ignored when
        the offset heads for the other edge.
    """
    mat = material if isinstance(material, Material) else get_material(material)
    validate_resting_potential_V(mat, resting_potential_V)
    measured = capacitance_uF_cm2 is not None
    if capacitance_uF_cm2 is None:
        capacitance_uF_cm2 = effective_capacitance_uF_cm2(
            mat, anodic_first=anodic_first_for_capacitance
        )
    excursion = polarisation_V(charge_density_uC_cm2, capacitance_uF_cm2)
    polarity = "anodic" if anodic_first else "cathodic"
    sign = 1.0 if anodic_first else -1.0
    peak = resting_potential_V + sign * excursion

    drift = None
    if (
        mat.water_window is not None
        and net_dc_current_uA is not None
        and area_cm2 is not None
        and train_duration_s is not None
    ):
        # The net offset drives toward the leading phase's edge when the leading phase
        # dominates, and toward the other one when the return phase over-recovers.
        drift_anodic = anodic_first if net_dc_current_uA >= 0.0 else not anodic_first
        headroom = drift_headroom_V(
            mat.water_window, resting_potential_V, anodic=drift_anodic
        )
        # The offset is stored on the branch it heads for (ledger 141): the leading
        # polarity's for under-recovery, the opposite one's for over-recovery. A measured
        # capacitance is one value, and so is the polarity-blind default (ledger 8).
        drift_capacitance = capacitance_uF_cm2
        if (
            not measured
            and anodic_first_for_capacitance is not None
            and drift_anodic != anodic_first_for_capacitance
        ):
            drift_capacitance = effective_capacitance_uF_cm2(mat, anodic_first=drift_anodic)
        drift = DcDrift(
            net_dc_current_uA=net_dc_current_uA,
            window_headroom_V=headroom,
            window_charge_uC=window_charge_uC(headroom, drift_capacitance, area_cm2),
            train_duration_s=train_duration_s,
            riding_charge_uC=(
                recovered_charge_uC if drift_anodic == anodic_first else 0.0
            ),
        )

    return WaterWindowResult(
        material_key=mat.key,
        window=mat.water_window,
        resting_potential_V=resting_potential_V,
        excursion_V=excursion,
        peak_potential_V=peak,
        polarity=polarity,
        capacitance_uF_cm2=capacitance_uF_cm2,
        drift=drift,
    )


def max_charge_density_in_window_uC_cm2(
    material: Material | str,
    *,
    anodic_first: bool = False,
    resting_potential_V: float = 0.0,
    capacitance_uF_cm2: float | None = None,
) -> float:
    """Charge density that just reaches the window boundary under the capacitive model.

    Returns ``inf`` when the material has no window on record. Raises ``ValueError`` when
    ``resting_potential_V`` is outside the material's window -- this function used to
    answer 1400 uC/cm^2 "allowed" for a platinum interface resting 4.2 V past its anodic
    limit (ledger 14). See :func:`validate_resting_potential_V`.
    """
    mat = material if isinstance(material, Material) else get_material(material)
    validate_resting_potential_V(mat, resting_potential_V)
    if mat.water_window is None:
        return math.inf
    if capacitance_uF_cm2 is None:
        # Polarity-specific: Rose & Robblee define both platinum limits by the same
        # window criterion, so a different charge density reaches it depending on which
        # reactions the leading phase can access. The capacitance follows suit.
        capacitance_uF_cm2 = effective_capacitance_uF_cm2(
            mat, anodic_first=anodic_first
        )
    if anodic_first:
        available_V = mat.water_window.anodic_V - resting_potential_V
    else:
        available_V = resting_potential_V - mat.water_window.cathodic_V
    if available_V <= 0:
        return 0.0
    return available_V * capacitance_uF_cm2
