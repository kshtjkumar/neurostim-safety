"""Stimulator compliance voltage.

A constant-current stimulator can only hold its commanded current while it has enough
voltage headroom to push that current through the total series impedance. When the
required voltage exceeds the compliance voltage the current source drops out of
regulation and delivers *less* current than commanded -- silently, in most hardware.
Every safety margin computed elsewhere in this package then describes a protocol that
was never actually delivered.

The voltage budget modelled here is

.. math::

    V_{required} = I\\,(R_{access} + R_{lead}) + \\Delta V_{polarisation}

- ``R_access`` is the ohmic spreading resistance into tissue, from the electrode
  geometry (Newman 1966 for a disc; exact forms for sphere and hemisphere; the equal-area
  sphere for immersed bodies such as the DBS band, +0.6 % above a converged solve at the
  clinical aspect and high at every aspect -- see ``Electrode.access_resistance_ohm``).
- ``R_lead`` is the series resistance of the lead wire and connectors, which is
  measurable and often non-negligible for long thin microwires.
- ``Delta V_polarisation`` is the interfacial excursion from the water-window module,
  computed under the same conservative pure-capacitance assumption.

**The return path** (ledger 5, fix plan D7). Current leaves through a counter electrode,
and a two-terminal pair has two interfaces and two spreading resistances. Supply
``counter_electrode`` and ``counter_separation_um`` and the budget becomes

.. math::

    V = I\\,(R_a + R_c - 2/(G \\sigma d) + R_{lead}) + \\Delta V_a + \\Delta V_c

**The return phase** (ledgers 4, 135). The return phase has its own ohmic term,
``I_ret (R ...)``, at its own amplitude. Its polarisation is only the **overshoot** past
rest. A return phase recovering no more than the leading charge just discharges the
interface back along the leading polarity's branch: the stored voltage opposes the drive,
and the stimulator needs no more than ``I_ret R``. For under-recovery that is an upper
bound, conservative by at most the residual ``(1 - r_a)`` of the leading excursion. Charge
recovered beyond rest, ``(r_a - 1) Q``, reaches the opposite branch and polarises at that
branch's ``C_eff``, which is polarity-specific (Pt: 250 uF/cm^2 cathodic, 125 anodic): the
active electrode's opposite polarity and the counter's leading one. A measured
``capacitance_uF_cm2`` is one value and applies to the overshoot too. This is pinned
against a pulse-by-pulse integration of the same circuit (``tests/oracles/pulse_voltage``).
C3.9 gave the whole return charge the opposite polarity's ``C_eff``. That is not the
physics, and the reviewer who asked for it retracted the request.

**The train's DC offset** (ledger 140). A waveform that recovers less, or more, than it
injects leaves ``d = |1 - r_a| Q`` on each interface per pulse, and under the same
leak-free capacitor model the water-window drift clause uses, the offset is still there
when the next pulse starts. So pulse ``N`` starts ``(N - 1) d`` from rest, where ``N`` is
the number of pulses the train delivers, ``ceil(n_pulses)`` including ``train_duty_cycle``,
and infinite for continuous stimulation. The offset adds to the phase that drives the
interface further the same way. Under-recovery (and monophasic delivery) leaves it on the
leading polarity's branch, so it adds to the leading phase at the leading ``C_eff``.
Over-recovery leaves it on the opposite branch, so it adds to the return phase's overshoot
at the opposite ``C_eff``. The phase it opposes is left alone rather than credited. The
counter carries the same charge with the opposite sign, on its own area and material.
A balanced waveform (Charge balance's own test) has no offset, and its numbers are
unchanged.

The active electrode's offset term is capped at the water-window headroom toward the edge
it is heading for, from ``resting_potential_V``. Beyond it the interface is at the edge,
where the charge goes into electrolysis rather than into the voltage, and the Water window
check FAILs the waveform in its own right: the drift clause counts ``f T`` pulses, at least
as many as ``N`` here, and at the same branch's ``C_eff`` (ledger 141), so an offset that
reaches the headroom here has reached it there too. That is pinned by a sweep in both
directions of drift. Two cases are **not capped**, and a continuous unbalanced train then
needs an infinite voltage, a compliance ceiling of zero:

- the counter, because its water window is not assessed (ledger 133), so a cap would hide
  the voltage with nothing to FAIL in its place;
- a material with no water window (Ta2O5), for the same reason.

**One exception to "upper bound"** (ledger 144). The budget bounds the stepped circuit
from above except when an over-recovering pulse's leading phase already carries the
interface past the window edge. The excess, ``e = max(0, Q - Q_edge)`` with ``Q_edge`` the
charge the leading branch holds from rest to the edge, then goes to electrolysis, so the
return phase overshoots by up to ``(r_a - 1) Q + e`` rather than ``(r_a - 1) Q``. By the
stepping recurrence the budget is then low by at most ``min(N e / (C_opp A), H_opp)``.
Modelling it would add a second kink to the back-solve for a regime that never bears a
limit, so it is stated instead. ``e > 0`` means the peak clause of the Water window check
already FAILs at that amplitude, so the limiting current is unaffected. Only this check's
own figure, and the "instrument" figure in ``limiting_current_by_kind``, can be low
there. The guarantee is the bound in volts, which never exceeds ``H_opp``. A percentage
is only a search maximum: the largest found is 18.4 %, for a 100 um Pt disc,
cathodic-first, r_a = 1.05, return_phase_ratio = 0.5, one pulse of 100 uA x 200 us
(3.1019 V against the stepped 3.8000 V). The Phase 3d review found 17 % for Pt, r_a 1.1,
N = 4. Every case found is inside the bound and a Water window FAIL, and both facts are
pinned by tests (ledger 148 corrected an earlier "up to 6.7 %", which was the maximum of
one narrower sweep).

with each electrode's own access resistance, ``G = 4 pi`` in a full space or ``2 pi`` for
two electrodes flush on one insulating plane (the convention of
:attr:`~neurostim.geometry.base.Electrode.environment`), and each interface's own
polarisation. The counter's capacitance is derived from its own material at the opposite
phase polarity. The mutual term is first-order superposition of two compact sources, so
two identical immersed contacts are *not* twice one: two 3389 contacts at 2 mm give
431.6 ohm against a naive 658.9. At large separation it vanishes, and the requirement
exactly doubles.

**The counter's own limits** (ledger 133). With a counter supplied, the assessment also
checks the counter's charge injection. That is the limit-bearing "Counter charge injection"
check: the larger phase's charge over the counter's area, against its material's CIC for
the mirrored waveform. The counter's **water window and chronic dissolution threshold are
not assessed**. A counter smaller than the active electrode carries the same charge at a
higher density, and those two limits must be checked separately.

Without a counter electrode the arithmetic is the single-interface budget above,
unchanged. The check says so and is at best CAUTION, because under-estimating the
required voltage is the anti-conservative direction. The equilibrium-potential difference
between two dissimilar electrode materials is **not** modelled.

If you have measured the electrode impedance directly, pass it as
``measured_impedance_ohm``: that supersedes the geometric estimate, and the result
records which path was taken. An impedance measured at 1 kHz is the usual laboratory
number, and it is not the same quantity as the DC access resistance -- it already
folds in some interfacial capacitance -- so the two are reported separately rather
than blended.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..data import gabriel1996
from ..geometry.base import Electrode
from ..geometry.planar import RectangularElectrode
from ..geometry.volumetric import CylindricalBandElectrode, MicrowireElectrode
from ..materials import Material, get_material
from ..protocol import StimProtocol
from ..units import charge_uC
from ._limits import floor_to_pass, format_limit
from .charge import charge_density_uC_cm2
from .water_window import (
    drift_headroom_V,
    effective_capacitance_uF_cm2,
    polarisation_V,
    validate_resting_potential_V,
)


def _volts(value_V: float) -> str:
    """A voltage for a detail line, or ``"unbounded"`` for an infinite one (ledger 143)."""
    return f"{value_V:.3f} V" if math.isfinite(value_V) else "unbounded"


def train_offset_V(
    current_uA: float,
    *,
    pulse_width_us: float,
    offset_factor: float,
    area_cm2: float,
    capacitance_uF_cm2: float,
    cap_V: float = math.inf,
) -> float:
    """The DC offset the train has built up when its last pulse starts (ledger 140).

    ``offset_factor`` is ``(N - 1) |1 - r_a|``, the offset as a multiple of the leading
    charge; ``inf`` for a continuous unbalanced train and ``0.0`` for a balanced one.
    Linear in the amplitude up to ``cap_V`` and flat beyond it, so it is monotone. At zero
    amplitude it is zero, and an infinite factor gives the cap directly: no ``0 * inf``.
    """
    if offset_factor == 0.0 or current_uA == 0.0:
        return 0.0
    if math.isinf(offset_factor):
        return cap_V
    offset = charge_uC(current_uA, pulse_width_us) * offset_factor
    return min(
        polarisation_V(charge_density_uC_cm2(offset, area_cm2), capacitance_uF_cm2), cap_V
    )


def required_voltage_V(
    current_uA: float,
    *,
    total_resistance_ohm: float,
    pulse_width_us: float,
    area_cm2: float,
    capacitance_uF_cm2: float,
    counter_area_cm2: float = 0.0,
    counter_capacitance_uF_cm2: float = 0.0,
    offset_factor: float = 0.0,
    offset_cap_V: float = math.inf,
) -> float:
    """Voltage the stimulator must supply to deliver ``current_uA`` into this load.

    ``counter_area_cm2 = 0`` means no counter interface is modelled; otherwise the same
    charge polarises the counter over its own area (ledger 5).

    ``offset_factor`` is the train's DC offset when it builds on this phase's branch, as
    under-recovery does (ledger 140, :func:`train_offset_V`): capped at ``offset_cap_V`` on
    the active electrode, uncapped on the counter.

    One expression, used both to report the requirement and to back-solve the limit. The
    back-solve used to scale the requested current by the voltage ratio, which is exact in
    real arithmetic and not in floating point: of 36 measured (electrode, compliance,
    pulse width) combinations, 6 reported limits FAILed their own compliance check and 14
    more sat below the boundary. Sharing the expression is what makes
    :attr:`ComplianceResult.max_current_uA` an inverse of :attr:`ComplianceResult.passes`
    rather than an approximation of one.
    """
    ohmic = (current_uA * 1e-6) * total_resistance_ohm
    charge = charge_uC(current_uA, pulse_width_us)
    density = charge_density_uC_cm2(charge, area_cm2)
    required = ohmic + polarisation_V(density, capacitance_uF_cm2)
    if counter_area_cm2 > 0.0:
        counter_density = charge_density_uC_cm2(charge, counter_area_cm2)
        required += polarisation_V(counter_density, counter_capacitance_uF_cm2)
    if offset_factor:
        required += _offsets_V(
            current_uA,
            pulse_width_us=pulse_width_us,
            offset_factor=offset_factor,
            offset_cap_V=offset_cap_V,
            area_cm2=area_cm2,
            capacitance_uF_cm2=capacitance_uF_cm2,
            counter_area_cm2=counter_area_cm2,
            counter_capacitance_uF_cm2=counter_capacitance_uF_cm2,
        )
    return required


def _offsets_V(
    current_uA: float,
    *,
    pulse_width_us: float,
    offset_factor: float,
    offset_cap_V: float,
    area_cm2: float,
    capacitance_uF_cm2: float,
    counter_area_cm2: float,
    counter_capacitance_uF_cm2: float,
) -> float:
    """Both interfaces' train offsets on one phase: the active one capped, the counter not."""
    total = train_offset_V(
        current_uA,
        pulse_width_us=pulse_width_us,
        offset_factor=offset_factor,
        area_cm2=area_cm2,
        capacitance_uF_cm2=capacitance_uF_cm2,
        cap_V=offset_cap_V,
    )
    if counter_area_cm2 > 0.0:
        total += train_offset_V(
            current_uA,
            pulse_width_us=pulse_width_us,
            offset_factor=offset_factor,
            area_cm2=counter_area_cm2,
            capacitance_uF_cm2=counter_capacitance_uF_cm2,
        )
    return total


def return_required_voltage_V(
    current_uA: float,
    *,
    return_current_factor: float,
    total_resistance_ohm: float,
    pulse_width_us: float,
    overshoot_fraction: float,
    area_cm2: float,
    capacitance_uF_cm2: float,
    counter_area_cm2: float = 0.0,
    counter_capacitance_uF_cm2: float = 0.0,
    offset_factor: float = 0.0,
    offset_cap_V: float = math.inf,
) -> float:
    """Voltage the return phase needs, at a leading amplitude ``current_uA`` (ledger 135).

    ``I_ret R`` plus the polarisation of the **overshoot** only. Under the capacitor model
    the leading phase leaves the interface charged on its own polarity's branch, and a
    return phase recovering no more than that charge only discharges it back toward rest.
    The interface voltage then opposes the drive, so the stimulator never needs more than
    ``I_ret R``. Only charge recovered beyond rest, ``(r_a - 1) Q``, reaches the opposite
    branch, and it polarises at that branch's C_eff: ``capacitance_uF_cm2`` here is the
    active electrode's opposite-polarity value, and ``counter_capacitance_uF_cm2`` the
    counter's leading-polarity one.

    Before C2.2 the return phase was invisible. From C2.2 it was budgeted as a full
    excursion from rest, a conservative double count that equalled the leading term for a
    symmetric pulse. C3.9 then gave that fictitious excursion the opposite polarity's C_eff,
    which made the return phase bind every symmetric Pt pulse: the worked example went from
    0.8287 to 1.0550 V. The reviewer retracted the finding that prompted it.

    ``offset_factor`` is the train's DC offset when over-recovery builds it on the opposite
    branch, which this phase's overshoot extends (ledger 140).
    """
    ohmic = (current_uA * return_current_factor * 1e-6) * total_resistance_ohm
    overshoot = charge_uC(current_uA, pulse_width_us) * overshoot_fraction
    required = ohmic
    if overshoot > 0.0:
        required += polarisation_V(
            charge_density_uC_cm2(overshoot, area_cm2), capacitance_uF_cm2
        )
        if counter_area_cm2 > 0.0:
            required += polarisation_V(
                charge_density_uC_cm2(overshoot, counter_area_cm2),
                counter_capacitance_uF_cm2,
            )
    # Outside the overshoot's branch: at a subnormal amplitude the overshoot underflows to
    # zero while an infinite offset does not, and skipping it there broke monotonicity.
    if offset_factor:
        required += _offsets_V(
            current_uA,
            pulse_width_us=pulse_width_us,
            offset_factor=offset_factor,
            offset_cap_V=offset_cap_V,
            area_cm2=area_cm2,
            capacitance_uF_cm2=capacitance_uF_cm2,
            counter_area_cm2=counter_area_cm2,
            counter_capacitance_uF_cm2=counter_capacitance_uF_cm2,
        )
    return required


@dataclass(frozen=True)
class ComplianceResult:
    """Voltage budget for one pulse."""

    current_uA: float
    access_resistance_ohm: float
    lead_resistance_ohm: float
    total_resistance_ohm: float
    ohmic_drop_V: float
    polarisation_V: float
    required_V: float
    available_V: float | None
    resistance_source: str
    access_resistance_is_exact: bool
    pulse_width_us: float
    area_cm2: float
    capacitance_uF_cm2: float
    conductivity_note: str = ""
    return_phase_current_uA: float = 0.0
    return_phase_width_us: float = 0.0
    return_current_factor: float = 0.0
    """Return-phase amplitude as a multiple of the leading one; 0.0 when there is none.

    Stored rather than derived from the two amplitudes, because the back-solve needs the
    return phase at amplitudes the protocol was never configured at, and a division of one
    stored amplitude by another is not the expression the protocol used to make them.
    """
    return_required_V: float = 0.0
    """Voltage the return phase alone demands, at the configured amplitude."""
    counter_access_resistance_ohm: float = 0.0
    """The counter electrode's own spreading resistance; 0.0 when none is modelled."""
    mutual_resistance_ohm: float = 0.0
    """``2/(G sigma d)``, subtracted from the two access resistances."""
    counter_area_cm2: float = 0.0
    """The counter's geometric area; 0.0 means the monopolar budget (no counter)."""
    counter_capacitance_uF_cm2: float = 0.0
    counter_polarisation_V: float = 0.0
    """The counter interface's excursion at the configured amplitude, leading phase."""
    return_capacitance_uF_cm2: float = 0.0
    """The active interface's C_eff for an overshoot past rest, at the opposite polarity.

    0.0 means "the same as :attr:`capacitance_uF_cm2`", which is also what a measured
    ``capacitance_uF_cm2`` gives: one measurement, not split by polarity.
    """
    counter_return_capacitance_uF_cm2: float = 0.0
    """The counter's C_eff for an overshoot past rest, at the leading polarity."""
    overshoot_fraction: float = 0.0
    """``max(0, r_a - 1)``: the share of the leading charge the return phase carries past rest."""
    offset_pulses: float = 0.0
    """``N - 1``: the pulses before the last one, each leaving its residue (ledger 140).

    0.0 for a balanced waveform or a single pulse, ``inf`` for a continuous unbalanced train.
    """
    offset_factor: float = 0.0
    """``(N - 1) |1 - r_a|``: the train's offset as a multiple of the leading charge."""
    offset_on_return: bool = False
    """Whether the offset builds on the return phase's branch (over-recovery) or the leading one."""
    offset_cap_V: float = math.inf
    """The active electrode's water-window headroom toward the offset's edge; ``inf`` uncapped."""
    offset_V: float = 0.0
    """The active electrode's train offset at the configured amplitude, capped."""
    counter_offset_V: float = 0.0
    """The counter's train offset at the configured amplitude; never capped."""

    @property
    def counter_modelled(self) -> bool:
        """Whether the budget includes a counter electrode, or assumes one interface."""
        return self.counter_area_cm2 > 0.0

    @property
    def has_return_phase(self) -> bool:
        """Whether a second phase draws current through the same load.

        False for a monophasic pulse and for a biphasic one recovering no charge.
        """
        return self.return_current_factor > 0.0 and self.return_phase_width_us > 0.0

    def required_V_at(self, current_uA: float) -> float:
        """Voltage the stimulator must supply for the worse of the two phases.

        The quantity :attr:`max_current_uA` inverts, and the one :attr:`required_V` is at
        the configured amplitude. Both phases are linear in the leading amplitude, so the
        maximum of the two is too -- which is what keeps the closed-form seed exact.

        The return phase used to be invisible here (ledger 4): with
        ``return_phase_ratio = 0.2`` a 1000 uA protocol drives 5000 uA through the same
        access resistance and the check reported the leading phase's 0.524 V, when the
        return phase alone needs 2.59 V. A stimulator sized on that number drops out of
        regulation during the return phase, silently.
        """
        leading = required_voltage_V(current_uA, **self._leading_terms(offset=True))
        if not self.has_return_phase:
            return leading
        returning = return_required_voltage_V(
            current_uA, **self._returning_terms(offset=True)
        )
        return max(leading, returning)

    def _leading_terms(self, *, offset: bool) -> dict[str, Any]:
        """The leading phase's arguments; ``offset=False`` leaves out the train offset."""
        return {
            "total_resistance_ohm": self.total_resistance_ohm,
            "pulse_width_us": self.pulse_width_us,
            "area_cm2": self.area_cm2,
            "capacitance_uF_cm2": self.capacitance_uF_cm2,
            "counter_area_cm2": self.counter_area_cm2,
            "counter_capacitance_uF_cm2": self.counter_capacitance_uF_cm2,
            "offset_factor": (
                self.offset_factor if offset and not self.offset_on_return else 0.0
            ),
            "offset_cap_V": self.offset_cap_V,
        }

    def _returning_terms(self, *, offset: bool) -> dict[str, Any]:
        """The return phase's arguments; ``offset=False`` leaves out the train offset."""
        return {
            "return_current_factor": self.return_current_factor,
            "total_resistance_ohm": self.total_resistance_ohm,
            "pulse_width_us": self.pulse_width_us,
            "overshoot_fraction": self.overshoot_fraction,
            "area_cm2": self.area_cm2,
            "capacitance_uF_cm2": self.return_capacitance_uF_cm2 or self.capacitance_uF_cm2,
            "counter_area_cm2": self.counter_area_cm2,
            "counter_capacitance_uF_cm2": (
                self.counter_return_capacitance_uF_cm2 or self.counter_capacitance_uF_cm2
            ),
            "offset_factor": self.offset_factor if offset and self.offset_on_return else 0.0,
            "offset_cap_V": self.offset_cap_V,
        }

    def _seed_uA(self, available_V: float) -> float:
        """The amplitude at which the worse phase reaches ``available_V``, in real arithmetic.

        Without a train offset both phases are linear in the amplitude, and scaling the
        configured one by the voltage ratio is exact. The offset makes the phase it lands on
        ``a I + min(b I, H)`` (the active electrode, capped at ``H``) plus ``c I`` (the
        counter, uncapped), and that is inverted piece by piece. ``floor_to_pass`` then
        settles the seed onto the float boundary of the forward comparison, as before.
        """
        if not self.offset_factor:
            return self.current_uA * (available_V / self.required_V)
        seeds = [self._phase_seed_uA(available_V, returning=False)]
        if self.has_return_phase:
            seeds.append(self._phase_seed_uA(available_V, returning=True))
        return min(seeds)

    def _phase_seed_uA(self, available_V: float, *, returning: bool) -> float:
        terms = self._returning_terms if returning else self._leading_terms
        phase = return_required_voltage_V if returning else required_voltage_V
        with_offset = terms(offset=True)
        if not with_offset["offset_factor"]:
            return available_V / phase(1.0, **terms(offset=False))
        common = {
            "pulse_width_us": self.pulse_width_us,
            "offset_factor": with_offset["offset_factor"],
        }
        if math.isinf(with_offset["offset_factor"]):
            active_slope = math.inf
            counter_slope = math.inf if self.counter_modelled else 0.0
        else:
            active_slope = train_offset_V(
                1.0, **common, area_cm2=with_offset["area_cm2"],
                capacitance_uF_cm2=with_offset["capacitance_uF_cm2"],
            )
            counter_slope = (
                train_offset_V(
                    1.0, **common, area_cm2=self.counter_area_cm2,
                    capacitance_uF_cm2=with_offset["counter_capacitance_uF_cm2"],
                )
                if self.counter_modelled
                else 0.0
            )
        linear = phase(1.0, **terms(offset=False)) + counter_slope
        cap = self.offset_cap_V
        if math.isinf(linear):
            return 0.0
        if math.isinf(active_slope):
            # The active offset is at its cap for every positive amplitude.
            return 0.0 if available_V <= cap else (available_V - cap) / linear
        if math.isinf(cap) or available_V <= (linear * cap / active_slope) + cap:
            return available_V / (linear + active_slope)
        return (available_V - cap) / linear

    @property
    def evaluated(self) -> bool:
        """Whether a stimulator compliance voltage was supplied to compare against."""
        return self.available_V is not None

    @property
    def passes(self) -> bool:
        """Whether the stimulator can supply the required voltage.

        ``True`` when no compliance voltage was supplied -- the check did not run.
        """
        if self.available_V is None:
            return True
        return self.required_V <= self.available_V

    @property
    def headroom_V(self) -> float:
        """Volts of spare compliance; negative means the source will drop out."""
        if self.available_V is None:
            return math.inf
        return self.available_V - self.required_V

    @property
    def utilisation(self) -> float:
        """Required voltage as a fraction of available compliance."""
        if self.available_V is None or self.available_V <= 0:
            return math.inf
        return self.required_V / self.available_V

    @property
    def max_current_uA(self) -> float:
        """Largest current the stimulator can actually drive into this load.

        Solves ``V = I*R + (I*W/A)/C_dl`` for ``I``; because both terms are linear in
        current, that reduces to scaling the requested current by the voltage ratio -- and
        then the answer is settled onto the boundary of the *forward* comparison, which
        recomputes the voltage rather than scaling it. The two differ by up to an ulp and
        the difference is a reported maximum that fails its own check (ledger 9).
        """
        if self.available_V is None or self.required_V <= 0:
            return math.inf
        available_V = self.available_V
        return floor_to_pass(
            self._seed_uA(available_V),
            lambda current_uA: self.required_V_at(current_uA) <= available_V,
            name="Compliance voltage",
        )

    def describe(self) -> str:
        """Multi-line summary."""
        exact = "exact" if self.access_resistance_is_exact else "equal-area approx."
        lines = [
            f"Compliance voltage ({self.resistance_source})",
            f"  access R      {self.access_resistance_ohm:.0f} ohm ({exact})",
        ]
        if self.conductivity_note:
            lines.append(f"  {self.conductivity_note}")
        if self.counter_modelled:
            lines += [
                f"  counter R     {self.counter_access_resistance_ohm:.0f} ohm",
                f"  mutual        -{self.mutual_resistance_ohm:.0f} ohm (the two "
                f"electrodes share the medium)",
            ]
        else:
            lines.append(
                "  monopolar single-interface budget assumed; supply counter_electrode "
                "for a two-terminal estimate"
            )
        if self.lead_resistance_ohm:
            lines.append(f"  lead R        {self.lead_resistance_ohm:.0f} ohm")
        lines += [
            f"  ohmic drop    {self.ohmic_drop_V:.3f} V",
            f"  polarisation  {self.polarisation_V:.3f} V",
        ]
        if self.counter_modelled:
            lines.append(f"  counter pol.  {self.counter_polarisation_V:.3f} V")
        if self.offset_factor:
            phase = "return" if self.offset_on_return else "leading"
            cap = (
                f", capped at the {self.offset_cap_V:.3f} V water-window headroom"
                if math.isfinite(self.offset_cap_V)
                else ", uncapped (no water window)"
            )
            pulses = (
                f"after {self.offset_pulses:g} unbalanced pulses"
                if math.isfinite(self.offset_pulses)
                else "over a continuous unbalanced train"
            )
            lines.append(
                f"  train offset  {_volts(self.offset_V)} on the {phase} phase "
                f"{pulses}{cap}"
            )
            if self.counter_modelled:
                lines.append(
                    f"  counter off.  {_volts(self.counter_offset_V)} (uncapped: the "
                    f"counter's water window is not assessed)"
                )
        if self.has_return_phase:
            lines.append(
                f"  return phase  {_volts(self.return_required_V)} "
                f"({self.return_phase_current_uA:g} uA x "
                f"{self.return_phase_width_us:g} us)"
            )
        if math.isfinite(self.required_V):
            lines.append(f"  required      {self.required_V:.3f} V")
        else:
            lines.append(f"  required      {self.unbounded_reason}")
        if self.available_V is None:
            lines.append("  available     not specified -> check NOT EVALUATED")
        else:
            verdict = "PASS" if self.passes else "INSUFFICIENT"
            lines.append(f"  available     {self.available_V:.3f} V -> {verdict}")
            if math.isfinite(self.required_V):
                lines.append(
                    f"  headroom      {self.headroom_V:+.3f} V "
                    f"({self.utilisation * 100:.1f} % used)"
                )
            if self.max_current_uA == 0.0:
                lines.append(
                    "  no amplitude of this protocol is within the compliance voltage"
                )
            elif not self.passes:
                lines.append(
                    f"  the source will drop out of regulation above "
                    f"{format_limit(self.max_current_uA)} uA; delivered current will "
                    f"be lower "
                    f"than commanded"
                )
        return "\n".join(lines)

    @property
    def unbounded_reason(self) -> str:
        """Why no finite voltage suffices, as a sentence; ``""`` when one does (ledger 143).

        The only unbounded term is an uncapped train offset over a continuous train
        (ledger 140): the counter's, whose water window is not assessed, or the active
        electrode's on a material with no water window. Every surface that would print the
        requirement prints this instead, so none shows a bare ``inf``.
        """
        if math.isfinite(self.required_V):
            return ""
        causes = []
        if math.isinf(self.offset_cap_V):
            causes.append("the electrode's material has no water window to cap it")
        if self.counter_modelled:
            causes.append(
                "the counter electrode's water window is not assessed, so its offset is "
                "not capped"
            )
        return (
            "no finite voltage: a continuous unbalanced train leaves an unbounded DC "
            "offset, and " + " and ".join(causes)
        )


def evaluate(
    electrode: Electrode,
    protocol: StimProtocol,
    *,
    material: Material | str | None = None,
    tissue_conductivity_S_per_m: float = 0.35,
    lead_resistance_ohm: float = 0.0,
    compliance_V: float | None = None,
    measured_impedance_ohm: float | None = None,
    capacitance_uF_cm2: float | None = None,
    counter_electrode: Electrode | None = None,
    counter_separation_um: float | None = None,
    resting_potential_V: float = 0.0,
) -> ComplianceResult:
    """Compute the voltage a stimulator must supply to deliver ``protocol``.

    ``counter_electrode`` and ``counter_separation_um`` go together. See
    :func:`validate_counter` for what is refused and why. ``resting_potential_V`` sets the
    water-window headroom that caps the active electrode's train offset (ledger 140), and
    is checked against the material's window as the Water window check checks it.
    """
    validate_counter(
        electrode, counter_electrode, counter_separation_um, measured_impedance_ohm
    )
    if lead_resistance_ohm < 0 or not math.isfinite(lead_resistance_ohm):
        raise ValueError(
            f"lead_resistance_ohm must be finite and >= 0, got {lead_resistance_ohm!r}"
        )

    if measured_impedance_ohm is not None:
        if not math.isfinite(measured_impedance_ohm) or measured_impedance_ohm <= 0:
            raise ValueError(
                f"measured_impedance_ohm must be finite and > 0, "
                f"got {measured_impedance_ohm!r}"
            )
        access_r = measured_impedance_ohm
        source = "measured electrode impedance"
        is_exact = True
        conductivity_note = ""
    else:
        access_r = electrode.access_resistance_ohm(tissue_conductivity_S_per_m)
        source = f"geometric estimate at sigma = {tissue_conductivity_S_per_m:g} S/m"
        is_exact = electrode.access_resistance_is_exact
        gabriel_sigma = gabriel1996.conductivity_for_pulse(protocol.pulse_width_us)
        fold = tissue_conductivity_S_per_m / gabriel_sigma
        if fold > 1.5:
            conductivity_note = (
                f"CAUTION: Gabriel et al. (1996) give {gabriel_sigma:.3f} S/m for grey "
                f"matter at the\n  effective frequency of a "
                f"{protocol.pulse_width_us:g} us pulse -- {fold:.1f}x below the "
                f"{tissue_conductivity_S_per_m:g} S/m used here.\n  Access resistance "
                f"scales as 1/sigma, so the required voltage could be {fold:.1f}x "
                f"higher."
            )
        else:
            conductivity_note = ""

    counter_r = 0.0
    mutual_r = 0.0
    counter_area = 0.0
    counter_capacitance = 0.0
    counter_return_capacitance = 0.0
    if counter_electrode is not None and counter_separation_um is not None:
        counter_r = counter_electrode.access_resistance_ohm(tissue_conductivity_S_per_m)
        factor = 2.0 * math.pi if electrode.environment == "half_space" else 4.0 * math.pi
        mutual_r = 2.0 / (factor * tissue_conductivity_S_per_m * counter_separation_um * 1e-6)
        counter_area = counter_electrode.area_cm2
        # The counter carries the opposite phase, so it sees the other polarity -- in the
        # leading phase the opposite of the protocol's, in the return phase the same.
        counter_mat = get_material(counter_electrode.material)
        counter_capacitance = effective_capacitance_uF_cm2(
            counter_mat, anodic_first=not protocol.anodic_first
        )
        counter_return_capacitance = effective_capacitance_uF_cm2(
            counter_mat, anodic_first=protocol.anodic_first
        )

    total_r = access_r + counter_r - mutual_r + lead_resistance_ohm
    current_A = protocol.current_uA * 1e-6
    ohmic = current_A * total_r

    # The material is resolved so that an unknown name fails here rather than silently
    # producing a voltage budget for an electrode that does not exist. It does not enter
    # the polarisation term itself: under the pure-capacitance interface model that term
    # depends only on charge density and the double-layer capacitance the caller chose.
    mat_key = material if material is not None else electrode.material
    mat = mat_key if isinstance(mat_key, Material) else get_material(str(mat_key))
    density = charge_density_uC_cm2(protocol.charge_per_phase_uC, electrode.area_cm2)
    # Same interfacial capacitance the water-window check uses: the polarisation term in
    # the voltage budget and the excursion inside the window are the same quantity.
    if capacitance_uF_cm2 is None:
        capacitance_uF_cm2 = effective_capacitance_uF_cm2(
            mat, anodic_first=protocol.anodic_first
        )
        # The return phase is the other polarity, whose C_eff differs for most materials
        # (Pt 250 cathodic against 125 anodic). A measured capacitance is one value and is
        # used for both phases.
        return_capacitance = effective_capacitance_uF_cm2(
            mat, anodic_first=not protocol.anodic_first
        )
    else:
        return_capacitance = capacitance_uF_cm2
    polar = polarisation_V(density, capacitance_uF_cm2)

    # The train's DC offset (ledger 140), gated on Charge balance's own test as the drift
    # clause is, so a balanced waveform is unchanged to the bit.
    validate_resting_potential_V(mat, resting_potential_V)
    residue = 1.0 - protocol.recovered_fraction
    offset_pulses = 0.0
    if not protocol.is_charge_balanced:
        offset_pulses = (
            math.inf
            if math.isinf(protocol.n_pulses)
            else float(max(math.ceil(protocol.n_pulses) - 1, 0))
        )
    offset_factor = offset_pulses * abs(residue) if offset_pulses else 0.0
    offset_on_return = residue < 0.0
    offset_cap = (
        math.inf
        if mat.water_window is None
        else drift_headroom_V(
            mat.water_window,
            resting_potential_V,
            anodic=protocol.anodic_first != offset_on_return,
        )
    )

    # The return phase's own budget. Its amplitude is a fixed multiple of the leading
    # one, taken from the protocol rather than divided out of two amplitudes, so the
    # back-solve can ask what the return phase does at an amplitude the protocol was
    # never configured at.
    return_factor = protocol.return_phase_current_at_uA(1.0)
    leading_required = required_voltage_V(
        protocol.current_uA,
        total_resistance_ohm=total_r,
        pulse_width_us=protocol.pulse_width_us,
        area_cm2=electrode.area_cm2,
        capacitance_uF_cm2=capacitance_uF_cm2,
        counter_area_cm2=counter_area,
        counter_capacitance_uF_cm2=counter_capacitance,
        offset_factor=0.0 if offset_on_return else offset_factor,
        offset_cap_V=offset_cap,
    )
    overshoot_fraction = max(0.0, protocol.recovered_fraction - 1.0)
    return_required = 0.0
    if return_factor > 0.0 and protocol.return_phase_width_us > 0.0:
        return_required = return_required_voltage_V(
            protocol.current_uA,
            return_current_factor=return_factor,
            total_resistance_ohm=total_r,
            pulse_width_us=protocol.pulse_width_us,
            overshoot_fraction=overshoot_fraction,
            area_cm2=electrode.area_cm2,
            capacitance_uF_cm2=return_capacitance,
            counter_area_cm2=counter_area,
            counter_capacitance_uF_cm2=counter_return_capacitance,
            offset_factor=offset_factor if offset_on_return else 0.0,
            offset_cap_V=offset_cap,
        )
    counter_polar = (
        polarisation_V(
            charge_density_uC_cm2(protocol.charge_per_phase_uC, counter_area),
            counter_capacitance,
        )
        if counter_area > 0.0
        else 0.0
    )

    return ComplianceResult(
        current_uA=protocol.current_uA,
        access_resistance_ohm=access_r,
        lead_resistance_ohm=lead_resistance_ohm,
        total_resistance_ohm=total_r,
        ohmic_drop_V=ohmic,
        polarisation_V=polar,
        required_V=max(leading_required, return_required),
        available_V=compliance_V,
        resistance_source=source,
        access_resistance_is_exact=is_exact,
        pulse_width_us=protocol.pulse_width_us,
        area_cm2=electrode.area_cm2,
        capacitance_uF_cm2=capacitance_uF_cm2,
        conductivity_note=conductivity_note,
        return_phase_current_uA=protocol.return_phase_current_uA,
        return_phase_width_us=protocol.return_phase_width_us,
        return_current_factor=return_factor,
        return_required_V=return_required,
        counter_access_resistance_ohm=counter_r,
        mutual_resistance_ohm=mutual_r,
        counter_area_cm2=counter_area,
        counter_capacitance_uF_cm2=counter_capacitance,
        counter_polarisation_V=counter_polar,
        return_capacitance_uF_cm2=return_capacitance,
        counter_return_capacitance_uF_cm2=counter_return_capacitance,
        overshoot_fraction=overshoot_fraction,
        offset_pulses=offset_pulses,
        offset_factor=offset_factor,
        offset_on_return=offset_on_return,
        offset_cap_V=offset_cap,
        offset_V=train_offset_V(
            protocol.current_uA,
            pulse_width_us=protocol.pulse_width_us,
            offset_factor=offset_factor,
            area_cm2=electrode.area_cm2,
            capacitance_uF_cm2=return_capacitance if offset_on_return else capacitance_uF_cm2,
            cap_V=offset_cap,
        ),
        counter_offset_V=(
            train_offset_V(
                protocol.current_uA,
                pulse_width_us=protocol.pulse_width_us,
                offset_factor=offset_factor,
                area_cm2=counter_area,
                capacitance_uF_cm2=(
                    counter_return_capacitance if offset_on_return else counter_capacitance
                ),
            )
            if counter_area > 0.0
            else 0.0
        ),
    )


def validate_counter(
    electrode: Electrode,
    counter_electrode: Electrode | None,
    counter_separation_um: float | None,
    measured_impedance_ohm: float | None = None,
) -> None:
    """Refuse a counter-electrode setting the two-terminal budget cannot honestly model.

    * a counter without a separation, or a separation without a counter: half an input;
    * a separation that is not finite, or not larger than the two electrodes' reaches (the
      larger of the equal-area radius and the enclosing sphere, :func:`_reach_um`): the
      superposition that gives the mutual term needs two separate bodies;
    * a half-space electrode with a full-space counter, or the reverse: no single
      superposition applies to one source flush in a plane and one immersed;
    * a counter with ``measured_impedance_ohm``: a measured impedance may already include
      the return path, and adding the counter's own resistance would count it twice.
    """
    if counter_electrode is None and counter_separation_um is None:
        return
    if counter_electrode is None:
        raise ValueError(
            "counter_separation_um was given without a counter_electrode"
        )
    if counter_separation_um is None:
        raise ValueError(
            "counter_electrode requires counter_separation_um (centre to centre, um)"
        )
    if not math.isfinite(counter_separation_um):
        raise ValueError(
            f"counter_separation_um must be finite, got {counter_separation_um!r}"
        )
    if counter_electrode.environment != electrode.environment:
        raise ValueError(
            f"counter_electrode is {counter_electrode.environment} and electrode is "
            f"{electrode.environment}: the mutual resistance of one source flush in a plane "
            f"and one immersed has no single superposition, so the two-terminal budget "
            f"cannot be computed"
        )
    if measured_impedance_ohm is not None:
        raise ValueError(
            f"measured_impedance_ohm ({measured_impedance_ohm!r} ohm) and counter_electrode "
            f"together are ambiguous: the measurement may already include the counter's "
            f"return path, and adding the counter's resistance would count it twice. "
            f"Supply one or the other"
        )
    closest = _reach_um(electrode) + _reach_um(counter_electrode)
    if counter_separation_um <= closest:
        raise ValueError(
            f"counter_separation_um ({counter_separation_um!r} um) must exceed the sum of "
            f"the electrode's and counter_electrode's reaches ({closest:.4g} um, each the "
            f"larger of its equal-area radius and its enclosing sphere): at "
            f"that distance the two overlap, and the superposition that gives the mutual "
            f"term needs two separate bodies"
        )


def _reach_um(electrode: Electrode) -> float:
    """How far an electrode extends from its centre, for the overlap guard.

    The larger of the equal-area substitute's radius and the radius of a sphere that
    encloses the body. The substitute alone is too small for an elongated body: a 3389
    band's equal-area sphere is 690 um across the middle, but the band is 1500 um long, so
    two on one shaft overlap below a 1500 um centre spacing (ledger 130).

    The enclosing radius is measured to the body's farthest point, not along its largest
    dimension alone (ledger 139). A rectangle reaches half its diagonal. A band, and a
    microwire's exposed shaft with its tip cap, reach their rim, ``sqrt(r^2 + (L/2)^2)``
    from the middle of the axial extent ``L`` (the exposed length plus the cap: ``r`` for
    a hemispherical tip, the cone height for a conical one). Discs, rings, spheres and
    hemispheres reach their outer radius. A separation is a centre distance with no
    orientation, so only an enclosing sphere guarantees two separate bodies. The price is
    that two coaxial 3389 bands are refused below 1965 um rather than 1500 um; the 2 mm
    clinical spacing is still accepted.
    """
    substitute = (
        electrode.equivalent_sphere_radius_um
        if electrode.environment == "full_space"
        else electrode.equivalent_radius_um
    )
    return max(substitute, _enclosing_radius_um(electrode))


def _enclosing_radius_um(electrode: Electrode) -> float:
    """Radius of a sphere about the body's centre that contains all of it, in um."""
    if isinstance(electrode, RectangularElectrode):
        return math.hypot(electrode.width_um, electrode.length_um) / 2.0
    if isinstance(electrode, CylindricalBandElectrode):
        return math.hypot(electrode.diameter_um / 2.0, electrode.height_um / 2.0)
    if isinstance(electrode, MicrowireElectrode):
        radius = electrode.diameter_um / 2.0
        if electrode.tip_shape == "hemispherical":
            cap = radius
        elif electrode.tip_shape == "conical":
            assert electrode.cone_height_um is not None  # required at construction
            cap = electrode.cone_height_um
        else:
            cap = 0.0
        return math.hypot(radius, (electrode.exposed_length_um + cap) / 2.0)
    return max(electrode.dimensions().values(), default=0.0) / 2.0
