"""Aggregate safety assessment and the :class:`SafetyCalculator` facade.

Individual checks live in sibling modules and each answer one question. This module
runs them together, applies a single status vocabulary, and refuses to collapse the
result into a bare "safe / unsafe" boolean: a protocol that clears the Shannon line but
exceeds the electrode's charge-injection limit is not safe, and one that clears both
but is monophasic is not safe either.

Status vocabulary
-----------------
``PASS``
    The check ran and the protocol is within the limit.
``CAUTION``
    The check ran and the protocol is within the limit, but a stated assumption is
    being stretched -- an unverified constant, a pulse width far from the measurement
    conditions, or a margin under the caution factor.
``FAIL``
    The check ran and the limit is exceeded.
``NOT_EVALUATED``
    The check could not run because a required input was not supplied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Literal

from ..data import cogan2016
from ..geometry.base import Electrode
from ..materials import Material, Policy, get_material
from ..protocol import StimProtocol
from ..uncertainty import Interval, most_restrictive
from ..units import charge_uC
from . import charge as charge_mod
from . import compliance as compliance_mod
from . import current_density as jd_mod
from . import envelope as envelope_mod
from . import shannon as shannon_mod
from . import water_window as ww_mod
from ._limits import floor_to_pass, format_limit
from .shannon import K_BOUNDS

CAUTION_MARGIN = 2.0
"""Margin below which a passing check is downgraded to CAUTION."""

CheckKind = Literal["tissue", "electrode-chronic", "electrode-acute", "instrument"]
"""What a limit is *about*. Four answers, and they are not interchangeable.

``tissue``
    An injury threshold measured in tissue -- Shannon's separatrix through cat cortex
    histology, Butterwick's electroporation threshold, Cogan's microelectrode
    charge-per-phase. Exceeding one is a statement about the patient.
``electrode-acute``
    A single-pulse property of the interface: the charge-injection capacity and the
    water window. Exceeding one drives irreversible reactions during the pulse.
``electrode-chronic``
    An accumulation over months of pulsing -- dissolution, and the DC an unbalanced
    waveform leaves behind. Relevant to an implant, not to one acute session.
``instrument``
    A property of the stimulator, not of the preparation. Programme above it and the
    protocol is not delivered as specified, which invalidates every other margin.

Reported alongside the single headline rather than instead of it: a user replacing a
stimulator cares about a different subset from a user choosing a chronic electrode
(physics M1a, M1c).
"""

CHECK_KINDS: dict[str, CheckKind] = {
    "Shannon criterion": "tissue",
    "Charge injection limit": "electrode-acute",
    "Water window": "electrode-acute",
    "Validated envelope": "tissue",
    "Current density": "tissue",
    "Microelectrode charge/phase": "tissue",
    "Chronic degradation": "electrode-chronic",
    "Charge balance": "electrode-chronic",
    "Compliance voltage": "instrument",
}
"""The kind of every check this package emits.

A table rather than an argument at each construction site: each builder below returns a
check from several branches, and a per-branch ``kind`` could disagree with itself about
what the same check is. The kind is a property of the question, not of the answer.
"""

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
"""The seven checks whose verdict depends on the amplitude, so each imposes a ceiling.

``Validated envelope`` and ``Charge balance`` are excluded, and the exclusion is load
bearing rather than tidy. Both are categorical properties of the parameter set -- how far
the protocol sits from the conditions the Shannon fit was derived at, and whether the
waveform recovers its charge -- so their verdicts do not move with current at all. A
monophasic protocol FAILs Charge balance at every amplitude, which is why the limiting
current is defined over this set and why an amplitude-independent failure has to be
reported as "no amplitude is safe" instead of as a number (ledger 84, fix plan D3).
"""


class Status(str, Enum):
    """Outcome vocabulary shared by every check."""

    PASS = "PASS"
    CAUTION = "CAUTION"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"

    @property
    def rank(self) -> int:
        """Severity ordering; higher is worse. NOT_EVALUATED sits *below* PASS.

        A check that did not run is not a finding. Ranking it above PASS made an overall
        PASS unreachable for any macroelectrode -- three of the nine checks do not apply
        above the macro/micro boundary, so the best attainable verdict was the same
        ``NOT_EVALUATED`` a completely unconfigured assessment returns, and the two were
        indistinguishable (ledger 11).

        Ordering NOT_EVALUATED lowest makes :attr:`SafetyAssessment.status` the worst
        verdict among the checks that *ran*, which is a statement about evidence. What the
        old ordering was reaching for -- do not let a bare PASS imply completeness -- is
        carried by :attr:`SafetyAssessment.not_evaluated` instead, which every headline
        surface renders beside the status.
        """
        return {
            Status.NOT_EVALUATED: 0,
            Status.PASS: 1,
            Status.CAUTION: 2,
            Status.FAIL: 3,
        }[self]


@dataclass(frozen=True)
class Check:
    """One named safety check with its status and human-readable detail."""

    name: str
    status: Status
    summary: str
    detail: str = ""
    margin: float = math.inf
    """Ratio of this check's own FAIL ceiling to the applied current.

    Above 1 means headroom; 0.5 means the protocol is at twice the ceiling; ``inf`` means
    the check imposes no ceiling, either because it bears none or because it did not run.

    **The FAIL ceiling, not the CAUTION ceiling, and not ``headroom / excursion``.** The
    difference is not cosmetic: on ``DiscElectrode(100, "Pt")`` at 200 us the chronic FAIL
    ceiling is 19.635 uA and the CAUTION ceiling 7.854; and the naive headroom reading of
    the water-window margin is **negative** (-21.095 uA where the truth is 58.905), which
    a finiteness test would accept.
    """
    ceiling_uA: float = math.inf
    """Largest amplitude at which this check is not in a FAIL state.

    Stored rather than recovered as ``margin * current_uA``: the limiting current is a
    minimum over these, and a product that is one ulp high would name a limit that FAILs
    its own check -- which is the defect the whole of Phase 1 is about.
    """
    provisional: bool = False
    """Whether the limit rests on a constant or model this package flags as unconfirmed.

    Travels with the margin so a caveated limit is visible *when it binds* (physics m6). A
    provisional limit is not a weaker limit; it is one whose number may move when the
    underlying measurement is made.
    """

    @property
    def kind(self) -> CheckKind:
        """What this check's limit is about; see :data:`CheckKind`."""
        try:
            return CHECK_KINDS[self.name]
        except KeyError:
            raise KeyError(
                f"no kind declared for check {self.name!r}; add it to CHECK_KINDS. "
                f"Every check must say whether its limit is about the tissue, the "
                f"electrode or the stimulator."
            ) from None

    def describe(self) -> str:
        """Multi-line rendering with the detail block indented."""
        head = f"[{self.status.value:>13}] {self.name}: {self.summary}"
        if not self.detail:
            return head
        body = "\n".join(f"    {line}" for line in self.detail.splitlines())
        return f"{head}\n{body}"


def _worst(statuses: list[Status]) -> Status:
    return max(statuses, key=lambda s: s.rank) if statuses else Status.NOT_EVALUATED


def _suffix(note: str) -> str:
    """``" (...)"`` for a non-empty note, ``""`` otherwise, so no trailing space is left."""
    return f" {note}" if note else ""


@dataclass(frozen=True)
class SafetyAssessment:
    """The full set of checks for one electrode / protocol pair."""

    electrode: Electrode
    protocol: StimProtocol
    material: Material
    checks: tuple[Check, ...]
    shannon: shannon_mod.ShannonResult
    charge: charge_mod.ChargeResult
    water_window: ww_mod.WaterWindowResult
    compliance: compliance_mod.ComplianceResult
    k: float
    policy: str

    @property
    def status(self) -> Status:
        """Worst status across all checks."""
        return _worst([c.status for c in self.checks])

    @property
    def failed(self) -> tuple[Check, ...]:
        """Checks that exceeded their limit."""
        return tuple(c for c in self.checks if c.status is Status.FAIL)

    @property
    def cautions(self) -> tuple[Check, ...]:
        """Checks that passed but with a stretched assumption or thin margin."""
        return tuple(c for c in self.checks if c.status is Status.CAUTION)

    @property
    def not_evaluated(self) -> tuple[Check, ...]:
        """Checks that could not run because a required input was not supplied.

        The companion to :attr:`Status.rank` putting NOT_EVALUATED below PASS: the
        headline is now the worst verdict among the checks that ran, so the set that did
        not run has to be reported alongside it or a bare ``PASS`` would claim more than
        was tested.
        """
        return tuple(c for c in self.checks if c.status is Status.NOT_EVALUATED)

    def not_evaluated_note(self) -> str:
        """Parenthetical naming the checks that did not run; empty when they all did.

        One renderer for every headline surface -- :meth:`describe`, the PDF, the JSON and
        the GUI -- so the four cannot drift apart.
        """
        missing = self.not_evaluated
        if not missing:
            return ""
        noun = "check" if len(missing) == 1 else "checks"
        names = ", ".join(c.name for c in missing)
        return f"({len(missing)} {noun} not evaluated: {names})"

    @property
    def unsafe_at_any_amplitude(self) -> tuple[Check, ...]:
        """FAILing checks that impose no ceiling, so no amplitude clears them.

        A check outside :data:`LIMIT_BEARING` has an amplitude-independent verdict by
        construction -- that is what bearing no limit means. If such a check FAILs, it
        FAILs at every amplitude, and the protocol is unsafe as a waveform rather than as
        an amplitude. A monophasic protocol is the case on record: it FAILs Charge balance
        at 1 fA and at 1 A alike, and the package still printed a limiting current of
        15.3 mA for it (ledger 84).

        The tuple rather than a boolean, because every surface has to **name** the check:
        "no amplitude is safe" without saying which check makes it so tells a user nothing
        they can act on.

        Distinct from ``limits_incomplete``, and deliberately not merged with it: that one
        says *the number may be too high, a candidate was missing*, this one says *there is
        no number*. One flag would force one rendering on two opposite messages.
        """
        return tuple(
            c
            for c in self.checks
            if c.status is Status.FAIL and c.name not in LIMIT_BEARING
        )

    def unsafe_at_any_amplitude_note(self) -> str:
        """Sentence naming why no amplitude is safe; empty when one is.

        One renderer for :meth:`describe`, ``report_to_json``, the PDF header and the GUI
        headline, so the four cannot disagree about what they are refusing to print.
        """
        checks = self.unsafe_at_any_amplitude
        if not checks:
            return ""
        names = ", ".join(c.name for c in checks)
        verb = "FAILs" if len(checks) == 1 else "FAIL"
        return f"no amplitude is safe: {names} {verb} at every amplitude"

    @property
    def _limit_bearing(self) -> tuple[Check, ...]:
        """The checks whose verdict moves with amplitude, in emission order."""
        return tuple(c for c in self.checks if c.name in LIMIT_BEARING)

    @property
    def limiting_current_uA(self) -> float:
        """Highest amplitude at which no limit-bearing check FAILs.

        The minimum over all seven of :data:`LIMIT_BEARING`, not over the three it used to
        be. Shannon, charge injection and compliance were the whole candidate set while
        nine checks ran, so four computed ceilings could not reach the headline: on the
        worked example that reported 141.37 uA while Microelectrode charge/phase (ceiling
        20.0) and Chronic degradation (70.69) were both FAILing at 80 uA -- a 7.07x
        overstatement, independently confirmed by binary search (ledger 1, 66).

        **This is not the same as "safe", and it is not the number to programme against
        without reading the rest.** Three things qualify it, each with its own field
        because each carries a different instruction:

        * :attr:`unsafe_at_any_amplitude` -- there is no safe amplitude at all, and this
          number must not be presented;
        * :attr:`limits_incomplete` -- a limit-bearing check did not run, so the true
          limit may be lower than this;
        * :attr:`limiting_current_by_kind` -- which of tissue, electrode or stimulator
          actually binds, since a user can change one and not the others.

        A check that did not run contributes ``inf``, so it cannot bind; that is what
        makes :attr:`limiting_mechanism` always name a check that ran.
        """
        return min(c.ceiling_uA for c in self._limit_bearing)

    @property
    def limits_incomplete(self) -> bool:
        """Whether a limit-bearing check did not run, so the limit may be too high.

        Distinct from :attr:`unsafe_at_any_amplitude`, which says there is no number at
        all. This one says the number is real but computed over a candidate set known to
        be missing a member -- which is the same defect as ledger 1, arrived at by a
        different route, and so has to be visible rather than inferred.
        """
        return bool(self._limit_bearing_not_evaluated)

    @property
    def _limit_bearing_not_evaluated(self) -> tuple[str, ...]:
        return tuple(
            c.name for c in self.not_evaluated if c.name in LIMIT_BEARING
        )

    def limits_incomplete_note(self) -> str:
        """Sentence naming the limit-bearing checks that did not run; empty when all did.

        One renderer for :meth:`describe`, the JSON, the PDF header and the GUI headline.
        """
        missing = self._limit_bearing_not_evaluated
        if not missing:
            return ""
        noun = "check" if len(missing) == 1 else "checks"
        return (
            f"INCOMPLETE: {len(missing)} limit-bearing {noun} did not run "
            f"({', '.join(missing)}), so the true limit may be lower"
        )

    @property
    def limiting_current_by_kind(self) -> dict[str, float]:
        """The binding amplitude within each :data:`CheckKind`, separately.

        The scalar headline stays a single minimum -- programming above the compliance
        limit means the protocol is not delivered as specified, which invalidates every
        other margin -- but a single number cannot say *what to change*. A user who can
        fit a different stimulator, a user choosing a chronic electrode and a user
        choosing an amplitude for one acute session are constrained by different rows of
        this mapping (physics M1a, M1c).
        """
        by_kind: dict[str, float] = {}
        for check in self._limit_bearing:
            by_kind[check.kind] = min(
                by_kind.get(check.kind, math.inf), check.ceiling_uA
            )
        return by_kind

    @property
    def limiting_current_interval_uA(self) -> Interval:
        """Binding current limit as an interval over the published ranges.

        The point estimate in :attr:`limiting_current_uA` depends on arbitrary choices --
        a single Shannon ``k``, a single ``policy`` end of the material's range. This
        propagates the published ranges instead, reduced to whichever binds at each end.

        **Over the same candidate set as the point estimate**, which is the whole of this
        commit. It used to propagate only Shannon and the charge-injection range while the
        point estimate is a minimum over all seven limit-bearing checks, so the two were
        answers to different questions: the worked example reported a limit of 20.0 uA
        beside an interval of 141.37-212.06 uA that does not contain it. An interval that
        excludes its own point estimate is a second, contradictory answer rather than a
        wider statement of the same one.

        Two checks carry a genuine published band and contribute one: Shannon over
        ``k`` 1.5-2.0, and chronic degradation over its stored threshold band. The rest
        contribute their ceiling exactly -- not because they are certain, but because no
        source in this bibliography gives a range for them, and inventing one here would
        be the kind of unsourced number this package exists to avoid. A check that did not
        run contributes nothing at all.

        A wide result is not a defect of the calculation. It is what the literature
        actually supports, and narrowing it requires characterising your own electrodes.
        """
        candidates = [
            self._ceiling_interval_uA(check)
            for check in self._limit_bearing
            if check.status is not Status.NOT_EVALUATED
        ]
        if not candidates:  # pragma: no cover - Current density always evaluates
            return Interval.exact(math.inf)
        return most_restrictive(candidates)

    def _ceiling_interval_uA(self, check: Check) -> Interval:
        """One check's ceiling across whatever published range stands behind it."""
        if check.name == "Shannon criterion":
            return shannon_mod.max_current_interval_uA(
                self.electrode.area_cm2, self.protocol.pulse_width_us
            )
        if check.name == "Charge injection limit":
            if self.charge.max_current_interval_uA is not None:
                return self.charge.max_current_interval_uA
            # pragma: no cover - only if a caller builds ChargeResult by hand
            return Interval.exact(self.charge.max_current_uA)
        if check.name == "Chronic degradation":
            return _chronic_ceiling_interval_uA(
                self.material, self.protocol, self.electrode.area_cm2
            )
        return Interval.exact(check.ceiling_uA)

    @property
    def limiting_mechanism(self) -> str:
        """The name of the check that imposes :attr:`limiting_current_uA`.

        A check name, not a hand-written phrase. It used to be the minimum over three
        strings built here -- "Shannon tissue-damage criterion", "Pt charge-injection
        limit", "stimulator compliance voltage" -- which could and did name a check that
        never ran: ``DiscElectrode(40, "PEDOT")`` at 200 us reported 99.6724 uA
        "(Shannon tissue-damage criterion)" while the Shannon check was NOT_EVALUATED,
        because the criterion does not apply below the macro/micro boundary (ledger 1,
        §9b.1). A check that did not run now carries a ceiling of ``inf``, so it cannot
        be the minimum, and the name is looked up rather than composed.
        """
        return min(self._limit_bearing, key=lambda c: c.ceiling_uA).name

    def _published_range_note(self) -> str:
        """What the interval beside it does and does not span.

        When the binding check has no published range the interval collapses onto the
        point estimate, and saying "across published ranges" without saying so would read
        as a precision the literature does not supply.
        """
        if self.limiting_current_interval_uA.is_exact:
            return (
                f"(unchanged: {self.limiting_mechanism} has no published range; "
                f"Shannon k {K_BOUNDS[0]}-{K_BOUNDS[1]} and the material range were "
                f"propagated and do not bind)"
            )
        return (
            f"(Shannon k {K_BOUNDS[0]}-{K_BOUNDS[1]}, full material range, "
            f"chronic threshold band)"
        )

    def _by_kind_line(self) -> str:
        """The per-kind limits in a fixed order, so the line is stable run to run."""
        order = ("tissue", "electrode-acute", "electrode-chronic", "instrument")
        by_kind = self.limiting_current_by_kind
        return ", ".join(
            f"{kind} "
            + (
                "no limit"
                if math.isinf(by_kind[kind])
                else f"{format_limit(by_kind[kind])} uA"
            )
            for kind in order
            if kind in by_kind
        )

    def describe(self) -> str:
        """Full multi-line report."""
        lines = [
            "=" * 72,
            "NEUROSTIM SAFETY ASSESSMENT",
            "=" * 72,
            self.electrode.describe(),
            "",
            self.protocol.describe(),
            "",
            f"Overall: {self.status.value}{_suffix(self.not_evaluated_note())}",
        ]
        # In place of a number, not beside one: a reader who sees an amplitude will
        # programme it, however the sentence next to it is worded. The interval goes with
        # it, for the same reason -- it is two more amplitudes.
        refusal = self.unsafe_at_any_amplitude_note()
        if refusal:
            lines.append(f"Limiting current: none -- {refusal}")
        else:
            lines += [
                f"Limiting current: {format_limit(self.limiting_current_uA)} uA "
                f"({self.limiting_mechanism})",
                f"  across published ranges: "
                f"{self.limiting_current_interval_uA.describe('uA', floor=True)} "
                f"{self._published_range_note()}",
                f"  by kind: {self._by_kind_line()}",
            ]
            incomplete = self.limits_incomplete_note()
            if incomplete:
                lines.append(f"  {incomplete}")
        lines += [
            "",
        ]
        lines += [c.describe() for c in self.checks]
        lines += [
            "",
            "-" * 72,
            "NOT a validated clinical or regulatory device calculation. Every limit "
            "here is an\nempirical or modelled estimate; see the per-check conditions "
            "and the bibliography.",
            "-" * 72,
        ]
        return "\n".join(lines)


# --- per-check ceilings ------------------------------------------------------------
#
# Every limit-bearing check needs the largest amplitude at which it does not FAIL, or the
# minimum in `limiting_current_uA` cannot see it. Four of the seven already had one, as
# the back-solve behind their own result; the four below did not, and their `margin` was
# `inf` -- which is how a check that FAILs at 80 uA contributed nothing to a limit of
# 141 uA (ledger 1).
#
# Each is floored onto the boundary of that check's own forward comparison by
# `_limits.floor_to_pass`, so `margin * current` is the ceiling rather than a value near
# it, and so programming the reported limit cannot FAIL.


# --- construction-time validation of the settings ----------------------------------
#
# A setting that is not a number used to produce a verdict anyway. `compliance_V = -5.0`
# printed "needs 0.52 V but only -5.00 V available"; `nan` yielded FAIL by comparison
# accident (ledger 13). Worse, a blank `compliance_V` cell in a batch CSV arrives as `nan`,
# whose ceiling is `nan`, and `min()` silently discards it -- `min([141.0, nan])` is 141.0
# while `min([nan, 141.0])` is nan, so the answer depended on check order and the row was
# indistinguishable from a valid one (ledger 52).
#
# At construction, not at assess(): the calculator is passed around, serialised and
# rebuilt, and an object that cannot produce a meaningful answer should not exist. It also
# means a batch row fails where `assess_batch` catches it and records an ERROR row with
# the message, instead of producing a plausible number.


def _require_finite_above(name: str, value: float, floor: float, *, strict: bool) -> None:
    """Raise unless ``value`` is a real number on the right side of ``floor``."""
    ok = math.isfinite(value) and (value > floor if strict else value >= floor)
    if ok:
        return
    relation = f"> {floor:g}" if strict else f">= {floor:g}"
    raise ValueError(f"{name} must be finite and {relation}, got {value!r}")


def _margin_from_ceiling(ceiling_uA: float, current_uA: float) -> float:
    """Ceiling as a multiple of the applied current."""
    if current_uA <= 0 or not math.isfinite(current_uA):
        return math.inf
    return ceiling_uA / current_uA


def _water_window_ceiling_uA(
    result: ww_mod.WaterWindowResult, protocol: StimProtocol, area_cm2: float
) -> float:
    """Largest amplitude whose peak potential stays inside the window.

    Monotone in current only because the resting potential is inside the window, which
    ``SafetyCalculator`` now enforces at construction: from outside it, a small pulse
    drives the interface back in and a large one out the other side, and "the largest
    amplitude that passes" would not be the answer to any question (see
    ``water_window.validate_resting_potential_V``).
    """
    window = result.window
    if window is None:
        return math.inf
    sign = 1.0 if protocol.anodic_first else -1.0
    seed_density = ww_mod.max_charge_density_in_window_uC_cm2(
        result.material_key,
        anodic_first=protocol.anodic_first,
        resting_potential_V=result.resting_potential_V,
        capacitance_uF_cm2=result.capacitance_uF_cm2,
    )

    def stays_in_window(current_uA: float) -> bool:
        density = charge_mod.charge_density_uC_cm2(
            charge_uC(current_uA, protocol.pulse_width_us), area_cm2
        )
        excursion = ww_mod.polarisation_V(density, result.capacitance_uF_cm2)
        return window.contains(result.resting_potential_V + sign * excursion)

    return floor_to_pass(
        seed_density * area_cm2 / (protocol.pulse_width_us * 1e-6),
        stays_in_window,
        name="Water window",
    )


def _density_ceiling_uA(
    limit_uC_cm2: float, protocol: StimProtocol, area_cm2: float, *, name: str
) -> float:
    """Largest amplitude whose charge density stays at or below ``limit_uC_cm2``."""
    return floor_to_pass(
        limit_uC_cm2 * area_cm2 / (protocol.pulse_width_us * 1e-6),
        lambda current_uA: charge_mod.charge_density_uC_cm2(
            charge_uC(current_uA, protocol.pulse_width_us), area_cm2
        )
        <= limit_uC_cm2,
        name=name,
    )


def _chronic_ceiling_uA(
    material: Material, protocol: StimProtocol, area_cm2: float
) -> float:
    """Largest amplitude at or below the material's dissolution threshold."""
    threshold = material.chronic_threshold
    if threshold is None:
        return math.inf
    return _density_ceiling_uA(
        threshold.high_uC_cm2, protocol, area_cm2, name="Chronic degradation"
    )


def _chronic_ceiling_interval_uA(
    material: Material, protocol: StimProtocol, area_cm2: float
) -> Interval:
    """The dissolution ceiling across the published band, not at one end of it.

    ``ChronicThreshold`` stores a band -- 20-50 uC/cm^2 for platinum -- of which the upper
    end is where the check FAILs and the lower end where it starts to caution. Both ends
    are real published numbers, so the interval spans them.
    """
    threshold = material.chronic_threshold
    if threshold is None:
        return Interval.exact(math.inf)
    return Interval(
        _density_ceiling_uA(
            threshold.low_uC_cm2, protocol, area_cm2, name="Chronic degradation"
        ),
        _density_ceiling_uA(
            threshold.high_uC_cm2, protocol, area_cm2, name="Chronic degradation"
        ),
    )


def _current_density_ceiling_uA(
    result: jd_mod.CurrentDensityResult, area_cm2: float
) -> float:
    """Largest amplitude strictly below the electroporation threshold.

    Strictly: the check FAILs at ``applied >= threshold``, so the amplitude that lands
    exactly on the threshold is already a FAIL and the ceiling is the float below it.
    """
    comparison = result.threshold
    if comparison is None:  # pragma: no cover - evaluate() always supplies one
        return math.inf
    threshold = comparison.threshold_A_per_cm2
    return floor_to_pass(
        threshold * area_cm2 * 1e6,
        lambda current_uA: jd_mod.average_current_density_A_per_cm2(
            current_uA, area_cm2
        )
        < threshold,
        name="Current density",
    )


def _microelectrode_ceiling_uA(electrode: Electrode, protocol: StimProtocol) -> float:
    """Largest amplitude at or below Cogan 2016's microelectrode damage threshold.

    ``inf`` outside the microelectrode regime, and that is not a shortcut: above the
    boundary the check reports NOT_EVALUATED, and inside the transition band it reports
    CAUTION at every amplitude. In neither case is there an amplitude at which it starts
    to FAIL, so neither imposes a ceiling.
    """
    if not cogan2016.is_microelectrode(electrode.area_cm2):
        return math.inf
    threshold_nC = cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE
    return floor_to_pass(
        threshold_nC * 1e-3 / (protocol.pulse_width_us * 1e-6),
        lambda current_uA: charge_uC(current_uA, protocol.pulse_width_us) * 1e3
        <= threshold_nC,
        name="Microelectrode charge/phase",
    )


def _shannon_check(
    result: shannon_mod.ShannonResult,
    k: float,
    protocol: StimProtocol | None = None,
    area_cm2: float | None = None,
    envelope: envelope_mod.EnvelopeResult | None = None,
) -> Check:
    # Cogan et al. (2016): below the macro/micro boundary the charge-density /
    # charge-per-phase codependence does not hold, so reporting Shannon headroom here
    # would contradict the microelectrode check and give false reassurance.
    if area_cm2 is not None and cogan2016.is_microelectrode(area_cm2):
        return Check(
            name="Shannon criterion",
            status=Status.NOT_EVALUATED,
            summary=(
                f"not applicable: {area_cm2:.3g} cm^2 is below the macro/micro "
                f"boundary (k would read {result.k_metric:.2f})"
            ),
            detail=(
                "Cogan et al. (2016) show microelectrodes do not follow the Shannon "
                "codependence: damaging levels fall well below a k = 1.85 line while "
                "charge densities sit well above 30 uC/cm^2. Use the microelectrode "
                "charge-per-phase check instead."
            ),
        )

    extra: list[str] = []
    k_note = shannon_mod.k_warning(k)
    if k_note:
        extra.append(f"THRESHOLD: {k_note}")
    if protocol is not None:
        cond = shannon_mod.conditions_warning(
            protocol.pulse_width_us, protocol.frequency_hz
        )
        if cond:
            extra.append(f"CONDITIONS: {cond}")
    detail = result.describe()
    if extra:
        detail += "\n" + "\n".join(f"  {line}" for line in extra)

    if not result.passes:
        return Check(
            name="Shannon criterion",
            status=Status.FAIL,
            summary=(
                f"k = {result.k_metric:.2f} exceeds the {k:.2f} threshold; "
                f"max {format_limit(result.max_current_uA)} uA"
            ),
            detail=detail,
            margin=result.current_margin,
        )

    # A threshold above Shannon's own 1.5, or a protocol far from the conditions the
    # fit was derived under, is a stretched assumption even when the number passes.
    # Outside the validated envelope the criterion cannot return an unqualified PASS:
    # Shannon states the extrapolation is not established, so a bare pass would assert
    # more than the evidence supports.
    outside_envelope = envelope is not None and not envelope.supports_unqualified_pass
    stretched = bool(extra) or outside_envelope
    thin = result.current_margin < CAUTION_MARGIN
    status = Status.CAUTION if (stretched or thin) else Status.PASS
    notes = []
    if outside_envelope:
        notes.append("outside validated envelope")
    if thin:
        notes.append("margin below 2x")
    if k_note:
        # "threshold" is load-bearing. The summary already opens with the computed
        # metric, so a bare "k above Shannon's 1.5" reads as a claim about that number
        # -- and it is routinely negative, which flatly contradicts the note. The two
        # k's in this sentence are different quantities.
        notes.append("threshold k above Shannon's 1.5")
    suffix = f" ({', '.join(notes)})" if notes else ""
    return Check(
        name="Shannon criterion",
        status=status,
        summary=(
            f"k = {result.k_metric:.2f} at threshold {k:.2f}, "
            f"{result.current_margin:.2f}x headroom{suffix}"
        ),
        detail=detail,
        margin=result.current_margin,
    )


def _charge_check(result: charge_mod.ChargeResult) -> Check:
    if not result.passes:
        return Check(
            name="Charge injection limit",
            status=Status.FAIL,
            summary=(
                f"{result.charge_density_uC_cm2:.4g} uC/cm^2 exceeds the "
                f"{result.cic_limit_uC_cm2:.4g} uC/cm^2 limit for "
                f"{result.material_key}; max {format_limit(result.max_current_uA)} uA"
            ),
            detail=result.describe(),
            margin=result.margin,
        )
    # A limit the cited work argues against cannot return an unqualified PASS,
    # for the same reason a protocol outside the Shannon envelope cannot.
    stretched = (
        bool(result.condition_warning)
        or bool(result.policy_warning)
        or not result.verified
    )
    thin = result.margin < CAUTION_MARGIN
    status = Status.CAUTION if (stretched or thin) else Status.PASS
    return Check(
        name="Charge injection limit",
        status=status,
        summary=(
            f"{result.charge_density_uC_cm2:.4g} uC/cm^2 of "
            f"{result.cic_limit_uC_cm2:.4g} uC/cm^2 "
            f"({result.utilisation * 100:.0f} % used)"
        ),
        detail=result.describe(),
        margin=result.margin,
    )


def _water_window_check(result: ww_mod.WaterWindowResult) -> Check:
    if not result.evaluated:
        return Check(
            name="Water window",
            status=Status.NOT_EVALUATED,
            summary=f"no potential limits on record for {result.material_key}",
            detail=result.describe(),
        )
    if not result.passes:
        return Check(
            name="Water window",
            status=Status.FAIL,
            summary=(
                f"peak {result.peak_potential_V:+.2f} V leaves the window "
                f"by {abs(result.headroom_V):.2f} V"
            ),
            detail=result.describe(),
        )
    status = Status.CAUTION if result.headroom_V < 0.1 else Status.PASS
    return Check(
        name="Water window",
        status=status,
        summary=(
            f"peak {result.peak_potential_V:+.2f} V, "
            f"{result.headroom_V:.2f} V headroom"
        ),
        detail=result.describe(),
    )


def _envelope_check(result: envelope_mod.EnvelopeResult) -> Check:
    """How far the protocol sits outside the conditions the Shannon fit was derived at."""
    if result.inside:
        return Check(
            name="Validated envelope",
            status=Status.PASS,
            summary="protocol is within the conditions the damage criterion was fitted at",
            detail=result.describe(),
        )
    concerning = result.concerning
    if not concerning:
        return Check(
            name="Validated envelope",
            status=Status.PASS,
            summary=(
                f"{len(result.outside)} parameter(s) outside the fit conditions, all in "
                f"the safer direction"
            ),
            detail=result.describe(),
        )
    worst = max(concerning, key=lambda e: e.fold)
    extent = (
        "unbounded" if math.isinf(worst.fold) else f"{worst.fold:.1f}x"
    )
    others = (
        f" (+{len(concerning) - 1} more)" if len(concerning) > 1 else ""
    )
    return Check(
        name="Validated envelope",
        status=Status.CAUTION,
        summary=(
            f"{worst.parameter} {extent} outside the fit conditions in a direction "
            f"that reduces margin{others}"
        ),
        detail=result.describe(),
    )


def _current_density_check(result: jd_mod.CurrentDensityResult) -> Check:
    """Compare current density against the Butterwick electroporation threshold.

    The threshold comes from chick membrane and retina, so this never returns a bare
    PASS: crossing it is a FAIL, but staying under it is a CAUTION at best, because the
    margin is against a preparation that is not the one being stimulated.
    """
    comparison = result.threshold
    if comparison is None:  # pragma: no cover - evaluate() always supplies one
        return Check(
            name="Current density",
            status=Status.NOT_EVALUATED,
            summary=f"{result.average_A_per_cm2:.4g} A/cm^2, no threshold available",
            detail=result.describe(),
        )
    if comparison.exceeds:
        return Check(
            name="Current density",
            status=Status.FAIL,
            summary=(
                f"{comparison.applied_A_per_cm2:.4g} A/cm^2 is at or above the "
                f"{comparison.threshold_A_per_cm2:.4g} A/cm^2 electroporation threshold"
            ),
            detail=result.describe(),
            margin=comparison.margin,
        )
    return Check(
        name="Current density",
        status=Status.CAUTION if comparison.margin < CAUTION_MARGIN else Status.PASS,
        summary=(
            f"{comparison.applied_A_per_cm2:.4g} A/cm^2 of the "
            f"{comparison.threshold_A_per_cm2:.4g} A/cm^2 electroporation threshold "
            f"({comparison.utilisation * 100:.1f} % used, chick-tissue derived)"
        ),
        detail=result.describe(),
        margin=comparison.margin,
    )


def _regime_check(electrode: Electrode, protocol: StimProtocol) -> Check:
    """Whether the Shannon criterion is the right criterion for this electrode at all.

    Cogan et al. (2016) show that microelectrodes do not follow the charge-density /
    charge-per-phase codependence Shannon describes. Below the macro/micro boundary the
    governing quantity is charge per phase, with a damage threshold near 4 nC/ph, and
    the Shannon result reported alongside is not applicable.
    """
    area = electrode.area_cm2
    charge_nC = protocol.charge_per_phase_uC * 1e3
    threshold = cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE

    if cogan2016.is_microelectrode(area):
        detail = (
            f"Geometric area {area:.3g} cm^2 is below the "
            f"{cogan2016.MACRO_MICRO_BOUNDARY_AREA_CM2[0]:.0e} cm^2 macro/micro "
            f"boundary (Butterwick et al. 2007, via Cogan et al. 2016).\n"
            f"For microelectrodes the Shannon codependence does not apply: damaging "
            f"levels fall well below a k = 1.85 line while charge densities sit well "
            f"above 30 uC/cm^2.\n"
            f"Charge per phase is the governing quantity, threshold about "
            f"{threshold:g} nC/ph. Reported physiological thresholds are "
            f"{cogan2016.MICROELECTRODE_PHYSIOLOGICAL_THRESHOLD_NC_PER_PHASE[0]:g}-"
            f"{cogan2016.MICROELECTRODE_PHYSIOLOGICAL_THRESHOLD_NC_PER_PHASE[1]:g} "
            f"nC/ph on ~1000 um^2, so useful stimulation sits close to the limit."
        )
        if charge_nC > threshold:
            return Check(
                name="Microelectrode charge/phase",
                status=Status.FAIL,
                summary=(
                    f"{charge_nC:.3g} nC/phase exceeds the {threshold:g} nC/phase "
                    f"microelectrode damage threshold"
                ),
                detail=detail,
                margin=threshold / charge_nC if charge_nC else math.inf,
            )
        status = (
            Status.CAUTION if charge_nC > threshold / CAUTION_MARGIN else Status.PASS
        )
        return Check(
            name="Microelectrode charge/phase",
            status=status,
            summary=(
                f"{charge_nC:.3g} nC/phase of the {threshold:g} nC/phase threshold "
                f"({charge_nC / threshold * 100:.0f} % used); Shannon does not apply "
                f"at this size"
            ),
            detail=detail,
            margin=threshold / charge_nC if charge_nC else math.inf,
        )

    if cogan2016.in_regime_transition(area):
        return Check(
            name="Microelectrode charge/phase",
            status=Status.CAUTION,
            summary=(
                f"area {area:.3g} cm^2 sits in the macro/micro transition band; "
                f"neither criterion is clearly the right one"
            ),
            detail=(
                f"The boundary reported by Butterwick et al. (2007) spans "
                f"{cogan2016.MACRO_MICRO_BOUNDARY_AREA_CM2[0]:.0e} to "
                f"{cogan2016.MACRO_MICRO_BOUNDARY_AREA_CM2[1]:.0e} cm^2. Charge per "
                f"phase here is {charge_nC:.3g} nC against a {threshold:g} nC/ph "
                f"microelectrode threshold; the Shannon result is also reported above."
            ),
        )

    return Check(
        name="Microelectrode charge/phase",
        status=Status.NOT_EVALUATED,
        summary=(
            f"area {area:.3g} cm^2 is a macroelectrode; the Shannon criterion applies"
        ),
    )


def _chronic_check(material: Material, charge_density_uC_cm2: float) -> Check:
    """Degradation thresholds that sit below the charge-injection limit."""
    threshold = material.chronic_threshold
    if threshold is None:
        return Check(
            name="Chronic degradation",
            status=Status.NOT_EVALUATED,
            summary=f"no degradation threshold on record for {material.key}",
        )
    if charge_density_uC_cm2 > threshold.high_uC_cm2:
        return Check(
            name="Chronic degradation",
            status=Status.FAIL,
            summary=(
                f"{charge_density_uC_cm2:.4g} uC/cm^2 exceeds the "
                f"{threshold.high_uC_cm2:g} uC/cm^2 {threshold.mechanism} threshold"
            ),
            detail=(
                f"{threshold.describe()}\n"
                f"This is a separate failure mode from the water window: the electrode "
                f"can stay inside its potential limits and still erode. Relevant to "
                f"chronic implants, not to a single acute session."
            ),
        )
    if charge_density_uC_cm2 > threshold.low_uC_cm2:
        return Check(
            name="Chronic degradation",
            status=Status.CAUTION,
            summary=(
                f"{charge_density_uC_cm2:.4g} uC/cm^2 is inside the "
                f"{threshold.low_uC_cm2:g}-{threshold.high_uC_cm2:g} uC/cm^2 "
                f"{threshold.mechanism} band"
            ),
            detail=threshold.describe(),
        )
    return Check(
        name="Chronic degradation",
        status=Status.PASS,
        summary=(
            f"{charge_density_uC_cm2:.4g} uC/cm^2 is below the "
            f"{threshold.low_uC_cm2:g} uC/cm^2 {threshold.mechanism} threshold"
        ),
        detail=threshold.describe(),
    )


def _charge_balance_check(protocol: StimProtocol) -> Check:
    if protocol.waveform == "monophasic":
        return Check(
            name="Charge balance",
            status=Status.FAIL,
            summary=(
                f"monophasic waveform injects "
                f"{protocol.net_dc_current_uA:.4g} uA net DC"
            ),
            detail=(
                "Monophasic stimulation accumulates unrecovered charge at the "
                "interface. Merrill et al. (2005) report significantly greater tissue "
                "damage from monophasic than from charge-balanced biphasic pulsing at "
                "matched charge density. No charge-density limit in this package is "
                "validated for monophasic delivery."
            ),
        )
    if not protocol.is_charge_balanced:
        return Check(
            name="Charge balance",
            status=Status.FAIL,
            summary=(
                f"{protocol.net_charge_per_pulse_uC:.4g} uC/pulse unrecovered "
                f"-> {protocol.net_dc_current_uA:.4g} uA DC"
            ),
            detail=(
                "Sustained DC drives irreversible faradaic reactions and electrode "
                "dissolution regardless of the per-phase charge density."
            ),
        )
    if protocol.interphase_gap_us > 0:
        detail = (
            f"Interphase gap of {protocol.interphase_gap_us:g} us. An open-circuit "
            f"interval between phases raises stimulation efficiency, because the "
            f"reversal phase is less able to abort the action potential the leading "
            f"phase initiated. It also leaves the interface unrecovered for that "
            f"interval, so a long gap trades efficiency against the time the electrode "
            f"spends polarised. Merrill et al. (2005) treat waveform shape as material "
            f"to charge recovery; no limit on gap duration is applied here because none "
            f"in this bibliography supports one."
        )
    else:
        detail = (
            "No interphase gap: the reversal phase follows immediately. This recovers "
            "charge soonest but is the least efficient waveform for a given charge, "
            "since the reversal phase can suppress the response the leading phase "
            "evoked."
        )
    return Check(
        name="Charge balance",
        status=Status.PASS,
        summary=(
            "biphasic, fully charge-balanced"
            + (
                f", {protocol.interphase_gap_us:g} us interphase gap"
                if protocol.interphase_gap_us
                else ""
            )
        ),
        detail=detail,
    )


def _compliance_check(result: compliance_mod.ComplianceResult) -> Check:
    if not result.evaluated:
        return Check(
            name="Compliance voltage",
            status=Status.NOT_EVALUATED,
            summary=(
                f"requires {result.required_V:.2f} V; no stimulator compliance "
                f"specified"
            ),
            detail=result.describe(),
        )
    if not result.passes:
        return Check(
            name="Compliance voltage",
            status=Status.FAIL,
            summary=(
                f"needs {result.required_V:.2f} V but only "
                f"{result.available_V:.2f} V available"
            ),
            detail=result.describe(),
            margin=result.max_current_uA / result.current_uA,
        )
    status = Status.CAUTION if result.utilisation > 0.8 else Status.PASS
    return Check(
        name="Compliance voltage",
        status=status,
        summary=(
            f"{result.required_V:.2f} V of {result.available_V:.2f} V "
            f"({result.utilisation * 100:.0f} % used)"
        ),
        detail=result.describe(),
        margin=result.max_current_uA / result.current_uA,
    )


class SafetyCalculator:
    """Facade running every electrochemical safety check for one electrode/protocol.

    The 0.1.0 attribute and method names (:attr:`charge_uC`, :attr:`charge_density`,
    :attr:`shannon_metric`, :attr:`max_charge_uC`, :attr:`max_current_shannon_uA`,
    :attr:`max_current_cic_uA`, :meth:`report`) are preserved, so existing scripts keep
    working. ``report()`` returns a superset of the original dictionary.
    """

    def __init__(
        self,
        electrode: Electrode,
        protocol: StimProtocol,
        k: float = shannon_mod.K_DEFAULT,
        *,
        material: Material | str | None = None,
        policy: Policy = "conservative",
        medium: str = "saline",
        tissue_conductivity_S_per_m: float = 0.35,
        lead_resistance_ohm: float = 0.0,
        compliance_V: float | None = None,
        measured_impedance_ohm: float | None = None,
        resting_potential_V: float = 0.0,
        capacitance_uF_cm2: float | None = None,
    ) -> None:
        shannon_mod.validate_k(k)
        _require_finite_above(
            "tissue_conductivity_S_per_m",
            tissue_conductivity_S_per_m,
            0.0,
            strict=True,
        )
        _require_finite_above("lead_resistance_ohm", lead_resistance_ohm, 0.0, strict=False)
        if compliance_V is not None:
            _require_finite_above("compliance_V", compliance_V, 0.0, strict=True)
        if measured_impedance_ohm is not None:
            _require_finite_above(
                "measured_impedance_ohm", measured_impedance_ohm, 0.0, strict=True
            )
        if capacitance_uF_cm2 is not None:
            _require_finite_above(
                "capacitance_uF_cm2", capacitance_uF_cm2, 0.0, strict=True
            )
        self.e = electrode
        self.p = protocol
        self.k = k
        self.policy: Policy = policy
        self.medium = medium
        self.tissue_conductivity_S_per_m = tissue_conductivity_S_per_m
        self.lead_resistance_ohm = lead_resistance_ohm
        self.compliance_V = compliance_V
        self.measured_impedance_ohm = measured_impedance_ohm
        self.resting_potential_V = resting_potential_V
        self.capacitance_uF_cm2 = capacitance_uF_cm2

        chosen = material if material is not None else electrode.material
        self.material = (
            chosen if isinstance(chosen, Material) else get_material(str(chosen))
        )
        # At construction, not at assess(): an electrode outside its own window at rest
        # makes the water-window verdict non-monotone in current, and every reported
        # limit here is "the largest amplitude that still passes". See
        # water_window.validate_resting_potential_V for the measurement behind it.
        ww_mod.validate_resting_potential_V(self.material, resting_potential_V)

    # --- 0.1.0 compatible surface --------------------------------------------

    @property
    def charge_uC(self) -> float:
        """Charge per phase in microcoulombs."""
        return self.p.charge_per_phase_uC

    @property
    def charge_density(self) -> float:
        """Charge density per phase in uC/cm^2."""
        return charge_mod.charge_density_uC_cm2(self.charge_uC, self.e.area_cm2)

    @property
    def shannon_metric(self) -> float:
        """The Shannon k value for this protocol."""
        return shannon_mod.shannon_k(self.charge_uC, self.e.area_cm2)

    @property
    def max_charge_uC(self) -> float:
        """Shannon-permitted charge per phase at the configured k."""
        return shannon_mod.shannon_max_charge_uC(self.e.area_cm2, self.k)

    @property
    def max_current_shannon_uA(self) -> float:
        """Shannon-permitted leading-phase current."""
        return shannon_mod.shannon_max_current_uA(
            self.e.area_cm2, self.p.pulse_width_us, self.k
        )

    @property
    def max_current_cic_uA(self) -> float:
        """Material charge-injection-permitted leading-phase current."""
        return charge_mod.cic_max_current_uA(
            self.material,
            self.e.area_cm2,
            self.p.pulse_width_us,
            self.policy,
            self.p.anodic_first,
        )

    # --- full assessment ------------------------------------------------------

    def assess(self) -> SafetyAssessment:
        """Run every check and return the aggregate assessment."""
        shannon_result = shannon_mod.evaluate(
            self.charge_uC, self.e.area_cm2, self.p.pulse_width_us, self.k
        )
        charge_result = charge_mod.evaluate(
            self.material,
            self.charge_uC,
            self.e.area_cm2,
            self.p.pulse_width_us,
            self.policy,
            self.medium,
            self.p.anodic_first,
        )
        envelope_result = envelope_mod.evaluate(self.p, self.e.area_cm2)
        n_pulses = (
            jd_mod.butterwick2007.PULSE_COUNT_SATURATION
            if math.isinf(self.p.n_pulses)
            else max(1, int(self.p.n_pulses))
        )
        jd_result = jd_mod.evaluate(
            self.p.current_uA,
            self.e.area_cm2,
            self.p.pulse_width_us,
            diameter_um=2.0 * self.e.equivalent_radius_um,
            n_pulses=n_pulses,
        )
        ww_result = ww_mod.evaluate(
            self.material,
            charge_result.charge_density_uC_cm2,
            anodic_first=self.p.anodic_first,
            resting_potential_V=self.resting_potential_V,
            capacitance_uF_cm2=self.capacitance_uF_cm2,
            anodic_first_for_capacitance=self.p.anodic_first,
        )
        compliance_result = compliance_mod.evaluate(
            self.e,
            self.p,
            material=self.material,
            tissue_conductivity_S_per_m=self.tissue_conductivity_S_per_m,
            lead_resistance_ohm=self.lead_resistance_ohm,
            compliance_V=self.compliance_V,
            measured_impedance_ohm=self.measured_impedance_ohm,
            capacitance_uF_cm2=self.capacitance_uF_cm2,
        )

        raw_checks = (
            _shannon_check(
                shannon_result, self.k, self.p, self.e.area_cm2, envelope_result
            ),
            _charge_check(charge_result),
            _water_window_check(ww_result),
            _envelope_check(envelope_result),
            _current_density_check(jd_result),
            _regime_check(self.e, self.p),
            _chronic_check(self.material, charge_result.charge_density_uC_cm2),
            _charge_balance_check(self.p),
            _compliance_check(compliance_result),
        )

        # The ceiling and the caveat are attached here rather than inside each builder:
        # a builder returns its check from up to four branches, and a per-branch ceiling
        # is four places for the same number to drift apart. A check that did not run
        # imposes no ceiling whatever its own back-solve says -- Shannon's max current is
        # a finite number on a microelectrode, where the check is NOT_EVALUATED because
        # the criterion does not apply.
        ceilings = {
            "Shannon criterion": shannon_result.max_current_uA,
            "Charge injection limit": charge_result.max_current_uA,
            "Water window": _water_window_ceiling_uA(
                ww_result, self.p, self.e.area_cm2
            ),
            "Current density": _current_density_ceiling_uA(jd_result, self.e.area_cm2),
            "Microelectrode charge/phase": _microelectrode_ceiling_uA(self.e, self.p),
            "Chronic degradation": _chronic_ceiling_uA(
                self.material, self.p, self.e.area_cm2
            ),
            "Compliance voltage": compliance_result.max_current_uA,
        }
        caveats = {
            # k above Shannon's own 1.5, a protocol far from the fit conditions, or a
            # protocol outside the validated envelope: the limit is computed, but the
            # criterion's authors do not stand behind the extrapolation.
            "Shannon criterion": bool(shannon_mod.k_warning(self.k))
            or bool(
                shannon_mod.conditions_warning(
                    self.p.pulse_width_us, self.p.frequency_hz
                )
            )
            or not envelope_result.supports_unqualified_pass,
            # An unverified constant, a pulse width far from the one it was measured at,
            # or a policy the source argues against.
            "Charge injection limit": bool(charge_result.condition_warning)
            or bool(charge_result.policy_warning)
            or not charge_result.verified,
            # The window itself may be provisional, and the interfacial capacitance is
            # derived from the material's own CIC unless the caller measured one.
            "Water window": ww_result.window is not None
            and not ww_result.window.verified,
            # Always. Butterwick's threshold is chick membrane and retina, so the margin
            # is against a preparation that is not the one being stimulated -- which is
            # also why this check never returns a bare PASS.
            "Current density": jd_result.threshold is not None,
            # The macro/micro boundary is itself a band; inside it neither criterion is
            # clearly the right one.
            "Microelectrode charge/phase": cogan2016.in_regime_transition(
                self.e.area_cm2
            ),
            # ChronicThreshold carries no `verified` field yet (ledger 30); when it does,
            # this reads it.
            "Chronic degradation": False,
            # An estimated access resistance is the dominant term in the voltage budget.
            "Compliance voltage": not compliance_result.access_resistance_is_exact,
        }
        checks = tuple(
            replace(
                check,
                ceiling_uA=ceiling,
                margin=_margin_from_ceiling(ceiling, self.p.current_uA),
                provisional=caveats.get(check.name, False),
            )
            for check, ceiling in (
                (
                    check,
                    math.inf
                    if check.status is Status.NOT_EVALUATED
                    else ceilings.get(check.name, math.inf),
                )
                for check in raw_checks
            )
        )
        return SafetyAssessment(
            electrode=self.e,
            protocol=self.p,
            material=self.material,
            checks=checks,
            shannon=shannon_result,
            charge=charge_result,
            water_window=ww_result,
            compliance=compliance_result,
            k=self.k,
            policy=self.policy,
        )

    def report(self) -> dict:
        """Flat dictionary of results.

        The six keys returned by the 0.1.0 prototype are preserved with the same
        meanings; everything else is additive.
        """
        assessment = self.assess()
        unsafe = assessment.unsafe_at_any_amplitude_note()
        return {
            # --- 0.1.0 keys ---
            "area_cm2": self.e.area_cm2,
            "charge_uC": self.charge_uC,
            "charge_density_uC_cm2": self.charge_density,
            "shannon_metric": self.shannon_metric,
            "max_current_shannon_uA": self.max_current_shannon_uA,
            "max_current_cic_uA": self.max_current_cic_uA,
            # --- added ---
            "material": self.material.key,
            "shannon_k_threshold": self.k,
            "cic_policy": self.policy,
            "cic_limit_uC_cm2": assessment.charge.cic_limit_uC_cm2,
            "max_charge_shannon_uC": self.max_charge_uC,
            "access_resistance_ohm": assessment.compliance.access_resistance_ohm,
            "required_compliance_V": assessment.compliance.required_V,
            "peak_electrode_potential_V": assessment.water_window.peak_potential_V,
            "duty_cycle": self.p.duty_cycle,
            "net_dc_current_uA": self.p.net_dc_current_uA,
            # None, not a number, when no amplitude is safe. A machine consumer is the
            # one that cannot read the caveat in the prose beside it, and this dict is
            # what becomes the columns of a batch CSV (ledger 84).
            "limiting_current_uA": (
                None if unsafe else assessment.limiting_current_uA
            ),
            "limiting_mechanism": unsafe or assessment.limiting_mechanism,
            "status": assessment.status.value,
        }

    def describe(self) -> str:
        """Full human-readable assessment."""
        return self.assess().describe()
