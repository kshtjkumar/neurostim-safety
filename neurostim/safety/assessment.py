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

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Literal, NamedTuple

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
from ._limits import LimitDidNotSettle, floor_to_pass, format_limit
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
    "Counter charge injection": "electrode-acute",
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
        "Counter charge injection",
    }
)
"""The eight checks whose verdict depends on the amplitude, so each imposes a ceiling.

Eight since C3.11 (ledger 133): the counter electrode's own charge injection is
amplitude-dependent, so it must bear a ceiling. Left outside, a verdict that moves with
amplitude would break the invariant that makes ``unsafe_at_any_amplitude`` correct (fix
plan D3, amended). It is emitted only when a counter electrode is supplied.

``Validated envelope`` and ``Charge balance`` are excluded, and the exclusion is load
bearing rather than tidy. Both are categorical properties of the parameter set -- how far
the protocol sits from the conditions the Shannon fit was derived at, and whether the
waveform recovers its charge -- so their verdicts do not move with current at all. A
monophasic protocol FAILs Charge balance at every amplitude, which is why the limiting
current is defined over this set and why an amplitude-independent failure has to be
reported as "no amplitude is safe" instead of as a number (ledger 84, fix plan D3).
"""


CeilingInterval = Callable[["SafetyAssessment", "Check"], Interval]
"""A limit-bearing check's ceiling across the published range that stands behind it."""


def _exact_ceiling(assessment: SafetyAssessment, check: Check) -> Interval:
    """No source in this bibliography gives a range for this check, so none is invented."""
    return Interval.exact(check.ceiling_uA)


def _shannon_ceiling_interval(assessment: SafetyAssessment, check: Check) -> Interval:
    """Shannon's ceiling over the whole ``k`` band he drew, 1.5-2.0."""
    return shannon_mod.max_current_interval_uA(
        assessment.electrode.area_cm2, assessment.protocol.pulse_width_us
    )


def _charge_ceiling_interval(assessment: SafetyAssessment, check: Check) -> Interval:
    """The charge-injection ceiling over the material's full published CIC range."""
    if assessment.charge.max_current_interval_uA is not None:
        return assessment.charge.max_current_interval_uA
    # pragma: no cover - only if a caller builds ChargeResult by hand
    return Interval.exact(assessment.charge.max_current_uA)


def _counter_charge_ceiling_interval(
    assessment: SafetyAssessment, check: Check
) -> Interval:
    """The counter's charge-injection ceiling over its material's published CIC range."""
    result = assessment.counter_charge
    if result is None or result.max_current_interval_uA is None:
        raise ValueError(
            "a Counter charge injection check exists but the assessment carries no counter "
            "charge result"
        )
    return result.max_current_interval_uA * (1.0 / _counter_charge_scale(assessment.protocol))


def _chronic_ceiling_interval(assessment: SafetyAssessment, check: Check) -> Interval:
    """The dissolution ceiling over the material's stored threshold band."""
    return _chronic_ceiling_interval_uA(
        assessment.material, assessment.protocol, assessment.electrode.area_cm2
    )


CEILING_INTERVALS: dict[str, CeilingInterval] = {
    "Shannon criterion": _shannon_ceiling_interval,
    "Charge injection limit": _charge_ceiling_interval,
    "Chronic degradation": _chronic_ceiling_interval,
    "Water window": _exact_ceiling,
    "Current density": _exact_ceiling,
    "Microelectrode charge/phase": _exact_ceiling,
    "Compliance voltage": _exact_ceiling,
    "Counter charge injection": _counter_charge_ceiling_interval,
}
"""How each :data:`LIMIT_BEARING` check's ceiling widens over its published range.

A table beside :data:`CHECK_KINDS` for the reason that one is a table, plus one more: the
lookup must *raise* on a name it does not know. It used to be three ``if check.name ==``
branches falling through to ``Interval.exact``, so a check whose name stopped matching
reported a point where the literature supports a band -- on ``DiscElectrode(100, "Pt")``
at 80 uA the chronic band 7.853-19.63 uA became 19.63 uA with nothing raised (ledger 97),
and the check names had already been rewritten wholesale once (ledger 95(a)). A check with
no published range therefore says so explicitly with :func:`_exact_ceiling`, rather than
reaching it by default; the keys are asserted equal to :data:`LIMIT_BEARING`.
"""


NO_SAFE_AMPLITUDE: frozenset[str] = frozenset({"Charge balance"})
"""Checks whose FAIL means no amplitude of this waveform is safe.

Named, never inferred from :data:`LIMIT_BEARING`'s complement, and the difference is a
defect waiting one commit away. Two checks sit outside ``LIMIT_BEARING`` and only one of
them carries this meaning. ``Charge balance`` FAILs when the waveform recovers no charge,
which no amplitude fixes: the argument is that no charge-density limit in this package was
measured on such a waveform, so every other verdict beside it is inapplicable.
``Validated envelope`` says the protocol sits outside the conditions the Shannon fit was
derived at, which is a statement about evidence rather than about safety at any amplitude.

It has no FAIL state today -- 60 CAUTION, 12 PASS and 0 FAIL over 72 swept configurations
-- which is the only reason the inferred definition looked correct. C2.5 rewrites that
check; the first time it FAILs, a protocol whose only fault is a high frequency would have
been announced as having no safe amplitude at all. "Bears no ceiling" and "failure means no
amplitude is safe" are different properties and the second is the one this is about, so it
is written down (review decision after ledger 99).
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
    biphasic_ceiling_uA: float = math.inf
    """The ceiling the same electrode and protocol report as a biphasic waveform.

    ``inf`` for a biphasic protocol, and for a monophasic one whose biphasic counterpart
    cannot be built -- a return phase doubles the active duration, which may no longer fit
    the period, and there is then no biphasic limit to compare against.

    A monophasic protocol is a strictly worse waveform, so it can never earn a higher
    limit than the biphasic one; :attr:`limit_bearing_ceiling_uA` takes the minimum. The
    cap is load bearing rather than decorative: refusing to apply a biphasic-measured
    charge-injection capacity to monophasic delivery removes a candidate from a minimum,
    which can only raise it. The DC-drift ceiling replaces that candidate for every
    material with a water window on record; Ta2O5 has none, and the cap is what holds its
    four inverted configurations (of 216 swept) at the biphasic value.
    """
    biphasic_mechanism: str | None = None
    """The check that binds the biphasic counterpart, named when the cap is what binds."""
    counter_charge: charge_mod.ChargeResult | None = None
    """The counter electrode's own charge-injection result; ``None`` without a counter."""

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
        """FAILing checks whose failure is a property of the waveform, not the amplitude.

        Membership of :data:`NO_SAFE_AMPLITUDE`, which is a named set and not
        ``LIMIT_BEARING``'s complement: see that constant for why the two are different
        questions and why reading one for the other is a defect one commit away. A
        monophasic protocol is the case on record -- it FAILs Charge balance at 1 fA and at
        1 A alike, and the package still printed a limiting current of 15.3 mA for it
        (ledger 84).

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
            if c.status is Status.FAIL and c.name in NO_SAFE_AMPLITUDE
        )

    @property
    def permits_no_current(self) -> tuple[Check, ...]:
        """Limit-bearing checks whose ceiling is zero, so they permit nothing at all.

        The second way a protocol has no safe amplitude, and the one the type did not
        carry. ``limiting_current_uA`` promised ``None`` whenever no amplitude is safe and
        returned ``0.0`` here, which every surface printed as ``Limiting current: 0 uA`` --
        an amplitude ``StimProtocol`` itself rejects, so the package named as a limit a
        value no user can set. 12 240 of 299 520 swept configurations produce one
        (ledger 99).

        Two real routes reach it: a resting potential exactly on the window edge, which
        :func:`water_window.validate_resting_potential_V` accepts deliberately because its
        boundary must agree with ``WaterWindow.contains``; and, since C2.3, a continuous
        train carrying any unrecovered charge, whose drift ceiling is exactly zero under a
        capacitive interface model.

        Non-positive rather than ``== 0.0``: a negative ceiling would be a worse statement
        of the same thing, and ``floor_to_pass`` returns non-positive values unchanged.
        """
        return tuple(
            c
            for c in self._limit_bearing
            if c.status is not Status.NOT_EVALUATED and c.ceiling_uA <= 0.0
        )

    def no_safe_amplitude_note(self) -> str:
        """Sentence naming why no amplitude is safe; empty when one is.

        One renderer for :meth:`describe`, ``report()``, ``report_to_json``, the PDF
        header, the GUI headline, the figure annotation and ``sensitivity``, so the seven
        cannot disagree about what they are refusing to print. Emptiness is the boolean
        :attr:`limiting_current_uA` branches on, so the sentence and the refusal cannot
        come apart.

        The two reasons are rendered as separate clauses because they carry different
        instructions: one says the *waveform* is wrong at any amplitude, the other names a
        limit that has closed to nothing under the settings given. A protocol can have
        both.
        """
        clauses = []
        waveform = self.unsafe_at_any_amplitude
        if waveform:
            names = ", ".join(c.name for c in waveform)
            verb = "FAILs" if len(waveform) == 1 else "FAIL"
            clauses.append(f"{names} {verb} at every amplitude")
        if self.limit_bearing_ceiling_uA <= 0.0:
            zero = self.permits_no_current
            names = (
                ", ".join(c.name for c in zero) if zero else self.limiting_mechanism
            )
            verb = "permits" if len(zero) <= 1 else "permit"
            clauses.append(f"{names} {verb} no current at all")
        if not clauses:
            return ""
        return "no amplitude is safe: " + "; ".join(clauses)

    @property
    def _limit_bearing(self) -> tuple[Check, ...]:
        """The checks whose verdict moves with amplitude, in emission order."""
        return tuple(c for c in self.checks if c.name in LIMIT_BEARING)

    @property
    def limiting_current_uA(self) -> float | None:
        """Highest amplitude that is safe to programme, or ``None`` when none is.

        ``None`` **exactly when** :meth:`no_safe_amplitude_note` has something to say --
        which is either :attr:`unsafe_at_any_amplitude` or :attr:`permits_no_current`. That
        is the whole of this property: the number itself is
        :attr:`limit_bearing_ceiling_uA`.

        The second half was a promise the attribute did not keep. A limit-bearing ceiling
        of exactly ``0.0`` returned a number, and every surface printed
        ``Limiting current: 0 uA`` -- an amplitude ``StimProtocol`` rejects at construction
        (ledger 99).

        The split is a repair, not a convenience. "Limiting current" in a safety package is
        read as *the highest amplitude you may use*, and for a protocol that FAILs a check
        at every amplitude there is no such amplitude -- yet the attribute returned
        15285.509415880857 uA for the monophasic band, with a mechanism name beside it
        (ledger 84). Nine consumers read it; six consulted the flag and three did not
        (ledger 89). Qualifying information one row away from where it is needed, carried
        across by nothing but a convention, is the shape of ledger 19, 59 and 60.

        ``float | None`` carries it structurally instead: ``mypy neurostim`` is a CI gate,
        so a consumer that does not handle the refusal stops typechecking rather than
        printing a number. C2.1 widens the refusal to unbalanced *biphasic* protocols, so
        the population of consumers that would have to remember grows before anyone
        re-audits them.

        ``None`` rather than a raise, because :attr:`limiting_current_by_kind`,
        :attr:`limiting_current_interval_uA` and :attr:`limiting_mechanism` are exactly
        what a user needs in order to diagnose a protocol that is unsafe as a *waveform*,
        and a raise would take all three with it.
        """
        if self.no_safe_amplitude_note():
            return None
        return self.limit_bearing_ceiling_uA

    @property
    def limit_bearing_ceiling_uA(self) -> float:
        """Minimum over the ceilings of the seven :data:`LIMIT_BEARING` checks.

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

        **Capped at the biphasic answer for a monophasic protocol** (ledger 2). See
        :attr:`biphasic_ceiling_uA`: a strictly worse waveform cannot earn a higher limit,
        and refusing to apply biphasic-measured charge-injection capacities to monophasic
        delivery would otherwise do exactly that.

        Always a float, and defined for every protocol including one no amplitude is safe
        for -- it is the quantity :attr:`limiting_current_by_kind` decomposes and the one
        the fail-ceiling oracle brackets. :attr:`limiting_current_uA` is this value with the
        refusal applied.

        :attr:`limiting_current_interval_uA` contains it whenever the monotonicity cap does
        not bind. The interval is built from this protocol's own checks, so when the
        biphasic cap binds this value can sit below the interval's low end: monophasic
        ``DiscElectrode(40, "Ta2O5")`` at 80 uA / 50 us gives 22.116812281272146 against
        ``[80.0, 80.0]`` (ledger 113). Not rendered, since the headline is ``None`` for
        every monophasic protocol.
        """
        return min(self._check_ceiling_uA, self.biphasic_ceiling_uA)

    @property
    def _check_ceiling_uA(self) -> float:
        """The minimum over the seven, before the monotonicity cap."""
        return min(c.ceiling_uA for c in self._limit_bearing)

    @property
    def monotonicity_capped(self) -> bool:
        """Whether the biphasic cap, rather than one of this protocol's own checks, binds."""
        return self.biphasic_ceiling_uA < self._check_ceiling_uA

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

        Three checks carry a genuine published band and contribute one: Shannon over
        ``k`` 1.5-2.0, charge injection over the material's published CIC range, and
        chronic degradation over its stored threshold band. The rest
        contribute their ceiling exactly -- not because they are certain, but because no
        source in this bibliography gives a range for them, and inventing one here would
        be the kind of unsourced number this package exists to avoid. Each check's
        contribution is declared in :data:`CEILING_INTERVALS`, and a check missing from it
        raises. A check that did not run contributes nothing at all.

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
        """One check's ceiling across whatever published range stands behind it.

        Raises ``KeyError`` for a check :data:`CEILING_INTERVALS` does not declare, the
        way :attr:`Check.kind` does: falling back to the point would silently narrow a
        published band (ledger 97).
        """
        try:
            provider = CEILING_INTERVALS[check.name]
        except KeyError:
            raise KeyError(
                f"no ceiling interval declared for check {check.name!r}; add it to "
                f"CEILING_INTERVALS. A check with no published range must declare "
                f"_exact_ceiling rather than reach it by default, or a renamed check "
                f"reports a point where the literature supports a band."
            ) from None
        return provider(self, check)

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

        When the monotonicity cap binds, the check named is the one that binds the
        *biphasic* counterpart -- which is the honest answer, because that is the limit
        being inherited. Still a check name, never a composed phrase;
        :attr:`monotonicity_capped` is how a surface knows to say where it came from.
        """
        if self.monotonicity_capped and self.biphasic_mechanism is not None:
            return self.biphasic_mechanism
        return min(self._limit_bearing, key=lambda c: c.ceiling_uA).name

    def monotonicity_cap_note(self) -> str:
        """Sentence saying the limit is inherited from the biphasic waveform; else empty."""
        if not self.monotonicity_capped:
            return ""
        return (
            f"capped at the biphasic limit ({self.biphasic_mechanism}): a monophasic "
            f"waveform is strictly worse and cannot earn a higher limit"
        )

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
        limit_uA = self.limiting_current_uA
        if limit_uA is None:
            lines.append(
                f"Limiting current: none -- {self.no_safe_amplitude_note()}"
            )
        else:
            lines += [
                f"Limiting current: {format_limit(limit_uA)} uA "
                f"({self.limiting_mechanism})",
                f"  across published ranges: "
                f"{self.limiting_current_interval_uA.describe('uA', floor=True)} "
                f"{self._published_range_note()}",
                f"  by kind: {self._by_kind_line()}",
            ]
            capped = self.monotonicity_cap_note()
            if capped:
                lines.append(f"  {capped}")
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


class _WindowSearch(NamedTuple):
    """Everything ``floor_to_pass`` needs for the water window, built in one place.

    The seed and the predicate are two expressions for one boundary -- a closed-form
    inversion and a forward comparison -- and ``floor_to_pass``'s contract is that they
    are inverses to within a few floats (ledger 9). Returning them together is what makes
    that contract assertable: a test can hand the seed to the predicate that it seeds,
    rather than re-deriving one of them and asserting against its own copy.

    That coupling is why the DC-drift clause and its inverse landed together. The clause
    FAILs when the interface leaves the window before the train ends, and the pulse-peak
    seed knew nothing about it: on the plan's own case the drift ceiling is
    ``Q_window / (PW . f . T) = 767.2735903959687`` uA (floored onto the check's own
    boundary: 767.2735903959689) against a peak-only seed of
    ``99745.56675147594`` uA -- a factor of ``f . T = 130``, 8.7e17 ulps, against a
    4-float budget, so ``floor_to_pass`` would have raised on every monophasic protocol.
    Landing the seed first was measured to be no better: 160 of 160 monophasic
    configurations then raise on the way *up*. ``TestTheWaterWindowSeedInvertsItsOwnPredicate``
    fails, naming ``_water_window_seed_uA``, if a third clause is ever added alone.
    """

    seed_uA: float
    """Largest amplitude every clause of :attr:`passes` admits, in closed form."""

    passes: Callable[[float], bool]
    """The forward comparison the seed must invert."""

    plateau_uA: float
    """Smallest change in current :attr:`passes` can resolve. See ``_limits.floor_to_pass``."""


def _water_window_seed_uA(
    result: ww_mod.WaterWindowResult, protocol: StimProtocol, area_cm2: float
) -> float:
    """Closed-form inverse of the water-window check: one term per clause, minimised.

    The check has two clauses and this has two terms. A clause added to the predicate
    must add its inverse here or the two stop being inverses of each other, and
    ``floor_to_pass`` raises rather than reporting a limit that fails its own check
    (ledger 9). ``TestTheWaterWindowSeedInvertsItsOwnPredicate`` fails, naming this
    function, if they come apart.

    **Peak excursion of one pulse.** ``seed_density * area / pulse_width_s``, where
    ``seed_density`` is the charge density that brings the interface exactly to the edge
    from rest.

    **DC drift over the train.** The amplitude at which ``t_exit`` equals
    ``train_duration_s``. ``t_exit = (window - riding) / I_dc`` with both ``riding`` and
    ``I_dc`` proportional to the amplitude, so::

        window_charge_uC / (riding_per_uA + net_dc_current_per_uA * train_duration_s)

    ``riding_per_uA`` is the recovered part of each pulse's charge, which peaks on top of
    the offset (ledger 105). It is exactly ``0.0`` for monophasic delivery and for
    over-recovery, which leaves the monophasic seed below unchanged bit for bit.

    with ``window_charge_uC = headroom_V * capacitance_uF_cm2 * area_cm2`` and
    ``net_dc_current_per_uA`` the net DC the waveform carries per microamp of leading
    amplitude, ``frac * pulse_width_s * frequency_hz``. Verified against the plan's own
    constants: ``0.6 V * 250 uF/cm^2 * 0.05984734 cm^2 = 8.9771 uC``, which at 35.1 uA is
    ``0.25576 s``, and ``8.9771 / (90e-6 * 130 * 1) = 767.2735903959687`` uA -- the seed,
    which ``floor_to_pass`` settles two ulps up at 767.2735903959689 -- against a
    peak-only 99745.56675147594 -- a factor of ``f * T = 130``, 8.7e17 ulps, against a
    four-float budget.

    A balanced waveform carries no DC, so the drift term is ``inf`` and does not bind. A
    continuous train drives it to ``0.0``, which ``floor_to_pass`` returns unchanged:
    under a capacitive interface model no amplitude of an unbalanced waveform survives an
    unbounded train, and ``0.0`` is the honest answer rather than a failure to find one.

    Both clauses are individually monotone-decreasing in current -- a larger amplitude
    means a larger excursion and a shorter time to the edge -- so their conjunction is too
    and ``floor_to_pass``'s precondition holds. That is true in floats as well as in exact
    arithmetic only because the unrecovered charge is one product, ``charge_uC(I, W) *
    (1 - r_a)`` (``StimProtocol.net_charge_at_uA``). As a difference of two products it
    was not: its rounding noise flickered the drift clause across consecutive floats and
    this docstring's claim was false (ledger 104).

    A drift this function cannot invert -- a result that says the waveform drifts while
    the protocol carries no DC per microamp -- raises. It used to become ``nan``, and
    ``min()`` silently discarded it (ledger 103).
    """
    seed_density = ww_mod.max_charge_density_in_window_uC_cm2(
        result.material_key,
        anodic_first=protocol.anodic_first,
        resting_potential_V=result.resting_potential_V,
        capacitance_uF_cm2=result.capacitance_uF_cm2,
    )
    pulse_width_s = protocol.pulse_width_us * 1e-6
    terms = [seed_density * area_cm2 / pulse_width_s]  # peak excursion of one pulse

    drift = result.drift
    if drift is not None and drift.drifts:
        dc_per_uA = abs(protocol.net_dc_current_at_uA(1.0))
        if not dc_per_uA > 0.0:
            raise LimitDidNotSettle(
                f"Water window: the result drifts at {drift.net_dc_current_uA!r} uA of net "
                f"DC, but the protocol carries {dc_per_uA!r} uA of DC per microamp of "
                f"leading amplitude, so the drift clause has no inverse to seed from."
            )
        riding_per_uA = _riding_charge_uC(drift, protocol, 1.0)
        terms.append(
            drift.window_charge_uC
            / (riding_per_uA + dc_per_uA * protocol.train_duration_s)
        )
    return min(terms)


def _riding_charge_uC(
    drift: ww_mod.DcDrift, protocol: StimProtocol, current_uA: float
) -> float:
    """The charge that rides on the offset at a given amplitude; see ``DcDrift``.

    Zero exactly when it is zero at the configured amplitude, so the seed, the predicate
    and the reported drift agree on whether anything rides.
    """
    if drift.riding_charge_uC == 0.0:
        return 0.0
    return charge_uC(current_uA, protocol.pulse_width_us) * protocol.recovered_fraction


def _water_window_search(
    result: ww_mod.WaterWindowResult, protocol: StimProtocol, area_cm2: float
) -> _WindowSearch:
    """The seed, the predicate it must invert, and the predicate's own resolution.

    Monotone in current only because the resting potential is inside the window, which
    ``SafetyCalculator`` now enforces at construction: from outside it, a small pulse
    drives the interface back in and a large one out the other side, and "the largest
    amplitude that passes" would not be the answer to any question (see
    ``water_window.validate_resting_potential_V``).
    """
    window = result.window
    if window is None:  # pragma: no cover - the caller returns inf before reaching here
        raise ValueError(f"{result.material_key} has no water window on record")
    sign = 1.0 if protocol.anodic_first else -1.0

    drift = result.drift

    def stays_in_window(current_uA: float) -> bool:
        density = charge_mod.charge_density_uC_cm2(
            charge_uC(current_uA, protocol.pulse_width_us), area_cm2
        )
        excursion = ww_mod.polarisation_V(density, result.capacitance_uF_cm2)
        if not window.contains(result.resting_potential_V + sign * excursion):
            return False
        # The second clause: what one pulse does, and then what the train does. An
        # unrecovered offset ramps the interface toward the edge whatever the peak
        # excursion is, and every per-pulse limit in this package was measured on a
        # waveform that leaves none behind (ledger 2).
        if drift is None or not drift.drifts:
            return True
        return not replace(
            drift,
            net_dc_current_uA=protocol.net_dc_current_at_uA(current_uA),
            riding_charge_uC=_riding_charge_uC(drift, protocol, current_uA),
        ).exits_during_train

    # The smallest change in current this predicate can resolve. It adds the excursion to
    # a *constant* resting potential and compares the sum against a window edge, so the
    # sum's ulp -- set by the largest potential in that arithmetic, not by the excursion
    # -- is a run of consecutive amplitudes the check cannot tell apart. With the resting
    # potential 1e-8 V inside platinum's edge the excursion at the boundary is 1e-8 V
    # while ulp(0.6 V) is 1.1e-16, so the run is ~4e7 floats wide and the seed lands
    # inside it. `floor_to_pass` bounds its climb relative to the seed, which shrinks with
    # the headroom while the run does not, so it raised `LimitDidNotSettle` on inputs C1.2
    # accepts: 4487 of 70831 edge-clustered configurations, every one of them here.
    # Converting one ulp of the sum back through the predicate's own chain gives the
    # climb the resolution the check actually has.
    plateau_uA = (
        math.ulp(
            max(
                abs(result.resting_potential_V),
                abs(window.cathodic_V),
                abs(window.anodic_V),
            )
        )
        * result.capacitance_uF_cm2
        * area_cm2
        / (protocol.pulse_width_us * 1e-6)
    )
    return _WindowSearch(
        seed_uA=_water_window_seed_uA(result, protocol, area_cm2),
        passes=stays_in_window,
        plateau_uA=plateau_uA,
    )


def _water_window_ceiling_uA(
    result: ww_mod.WaterWindowResult, protocol: StimProtocol, area_cm2: float
) -> float:
    """Largest amplitude whose peak potential stays inside the window."""
    if result.window is None:
        return math.inf
    search = _water_window_search(result, protocol, area_cm2)
    return floor_to_pass(
        search.seed_uA,
        search.passes,
        name="Water window",
        plateau=search.plateau_uA,
    )


def _check_caveat_keys(caveats: dict[str, bool]) -> None:
    """Every caveat key is a limit-bearing check; a misspelt key raises (ledger 137)."""
    unknown = sorted(set(caveats) - LIMIT_BEARING)
    if unknown:
        raise ValueError(
            f"caveat keys {unknown} name no limit-bearing check; LIMIT_BEARING is "
            f"{sorted(LIMIT_BEARING)}"
        )


def _provisional(caveats: dict[str, bool], name: str) -> bool:
    """Whether the check ``name`` is provisional, raising if a limit-bearing one has no entry.

    ``caveats.get(name, False)`` let a typo in a key make that limit silently
    non-provisional, and the full suite passed (ledger 137, the ledger 97 fall-through
    again). A check that bears no limit has no ceiling to caveat and is never provisional.
    """
    if name not in LIMIT_BEARING:
        return False
    try:
        return caveats[name]
    except KeyError:
        raise KeyError(
            f"no caveat declared for limit-bearing check {name!r}; add it to the caveats "
            f"in SafetyCalculator.assess"
        ) from None


def _counter_charge_scale(protocol: StimProtocol) -> float:
    """The larger phase's charge as a multiple of the leading one, for the counter.

    ``r_a`` when the return phase over-recovers, else 1: the counter carries both phases,
    and the larger density is the one its limit must hold.
    """
    return max(1.0, protocol.recovered_fraction)


def _counter_charge_ceiling_uA(
    result: charge_mod.ChargeResult, protocol: StimProtocol, area_cm2: float
) -> float:
    """Largest leading amplitude at which the counter's larger phase stays within its CIC."""
    limit = result.cic_limit_uC_cm2
    scale = _counter_charge_scale(protocol)
    return floor_to_pass(
        limit * area_cm2 / (protocol.pulse_width_us * 1e-6 * scale),
        lambda current_uA: charge_mod.charge_density_uC_cm2(
            charge_uC(current_uA, protocol.pulse_width_us) * scale, area_cm2
        )
        <= limit,
        name="Counter charge injection",
    )


def _counter_charge_check(
    result: charge_mod.ChargeResult, waveform: str, ceiling_uA: float
) -> Check:
    """The counter electrode's own charge-injection capacity (ledger 133).

    The counter sees the mirrored waveform: a cathodic-first protocol is anodic-first at the
    counter, and the stored CICs are keyed by the waveform's leading polarity, so ``result``
    was evaluated at the opposite polarity, with the same policy, medium and derating as the
    active electrode. Its charge is the larger of the two phases. Otherwise it is judged
    exactly as :func:`_charge_check` judges the active electrode, including NOT_EVALUATED for
    monophasic delivery. The counter's water window and chronic threshold are **not**
    assessed; see the compliance module docstring.
    """
    base = _charge_check(result, waveform)
    # The "max" in a FAIL summary is the leading amplitude the counter allows, which is the
    # charge result's own back-solve divided by the larger phase's share.
    summary = base.summary.replace(
        f"max {format_limit(result.max_current_uA)} uA", f"max {format_limit(ceiling_uA)} uA"
    )
    return replace(base, name="Counter charge injection", summary=f"counter electrode: {summary}")


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
    result: jd_mod.CurrentDensityResult, protocol: StimProtocol, area_cm2: float
) -> float:
    """Largest amplitude strictly below the electroporation threshold, for both phases.

    Strictly: the check FAILs at ``applied >= threshold``, so the amplitude that lands
    exactly on the threshold is already a FAIL and the ceiling is the float below it.

    One clause per phase, and the seed is the minimum of their two closed-form inverses --
    the same shape as the water window's, and for the same reason: the predicate is a
    conjunction, so the seed must invert every branch of it or ``floor_to_pass`` is handed
    a value its own forward comparison rejects by more than a rounding. The return phase's
    inverse carries the waveform's amplitude ratio, because the amplitude being solved for
    is the *leading* one: a return phase at ``k`` times the leading amplitude reaches its
    own threshold at ``1/k`` of the leading amplitude that would reach it.

    Both clauses are individually monotone-decreasing in the leading amplitude -- each is
    a positive multiple of it compared against a constant -- so their conjunction is too
    and ``floor_to_pass``'s precondition holds.
    """
    comparison = result.threshold
    if comparison is None:  # pragma: no cover - evaluate() always supplies one
        return math.inf
    threshold = comparison.threshold_A_per_cm2
    seeds = [threshold * area_cm2 * 1e6]

    return_comparison = result.return_threshold
    if return_comparison is not None:
        return_threshold = return_comparison.threshold_A_per_cm2
        # The leading amplitude at which the return phase reaches its own threshold.
        factor = protocol.return_phase_current_at_uA(1.0)
        seeds.append(return_threshold * area_cm2 * 1e6 / factor)

    def below_threshold(current_uA: float) -> bool:
        if (
            jd_mod.average_current_density_A_per_cm2(current_uA, area_cm2) >= threshold
        ):
            return False
        if return_comparison is None:
            return True
        return (
            jd_mod.average_current_density_A_per_cm2(
                protocol.return_phase_current_at_uA(current_uA), area_cm2
            )
            < return_comparison.threshold_A_per_cm2
        )

    return floor_to_pass(min(seeds), below_threshold, name="Current density")


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
    geometry_note: str = "",
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
    if geometry_note:
        extra.append(geometry_note)
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
    if geometry_note:
        notes.append("fit on discs, not this geometry")
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


def _charge_check(result: charge_mod.ChargeResult, waveform: str) -> Check:
    """The material's charge-injection capacity, for the waveform it was measured on.

    NOT_EVALUATED for a monophasic protocol, and that is the whole of ledger 2's first
    half. Every charge-injection capacity in this database was measured with a
    charge-balanced biphasic waveform (Merrill et al. 2005) -- the quantity is defined as
    the charge density reachable without driving irreversible reactions *given that the
    return phase recovers it*. Applying the number to delivery that recovers nothing
    asserts more than the measurement supports, in the anti-conservative direction.

    Removing a candidate from a minimum can only raise it, so this alone would let a
    strictly worse waveform earn a higher limit. Two things stop it: the DC-drift ceiling
    the water window gained at C2.3, which is the binding candidate for most materials, and
    the monotonicity cap in :meth:`SafetyCalculator.assess`, which holds the rest at the
    biphasic value. Measured over 216 configurations: this branch alone inverts 4 of them,
    every one Ta2O5 -- the single shipped material with no water window on record and
    therefore no drift ceiling -- and the cap closes exactly those.
    """
    if waveform == "monophasic":
        return Check(
            name="Charge injection limit",
            status=Status.NOT_EVALUATED,
            summary=(
                f"the {format_limit(result.cic_limit_uC_cm2)} uC/cm^2 limit for "
                f"{result.material_key} was measured with a charge-balanced biphasic "
                f"waveform; no source here validates it for monophasic delivery"
            ),
            detail=(
                "Merrill et al. (2005): a charge-injection capacity is the charge density "
                "reachable without irreversible reactions *given that the return phase "
                "recovers it*. Monophasic delivery recovers none, so the measurement does "
                "not describe it and the number is not applied.\n"
                + result.describe()
            ),
        )
    if not result.passes:
        return Check(
            name="Charge injection limit",
            status=Status.FAIL,
            summary=(
                f"{result.charge_density_uC_cm2:.4g} uC/cm^2 exceeds the "
                f"{format_limit(result.cic_limit_uC_cm2)} uC/cm^2 limit for "
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
            f"{format_limit(result.cic_limit_uC_cm2)} uC/cm^2 "
            f"({result.utilisation * 100:.0f} % used)"
        ),
        detail=result.describe(),
        margin=result.margin,
    )


def _water_window_check(result: ww_mod.WaterWindowResult) -> Check:
    """Two clauses: what one pulse does, and what the train leaves behind.

    The second is ledger 2. Every per-pulse limit in this package -- the charge-injection
    capacity, the Shannon criterion, the peak excursion below -- was measured or derived
    on a charge-balanced waveform, so none of them describes what an unrecovered offset
    does over a thousand pulses. The monophasic band at 3000 uA / 90 us / 130 Hz reported
    PASS with 0.58 V of headroom while the interface leaves its 0.6 V window in 0.256 s.

    A waveform that leaves charge behind never returns a bare PASS. Reaching the edge
    before the train ends is a FAIL; reaching it afterwards is a CAUTION with the time
    reported, because the model is a capacitor with no leakage and the real interface has
    some -- so the time is a lower bound on how long the offset is tolerable, not a
    licence.
    """
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
    drift = result.drift
    if drift is not None and drift.drifts:
        train = (
            "a continuous train"
            if math.isinf(drift.train_duration_s)
            else f"the {drift.train_duration_s:g} s train"
        )
        if drift.exits_during_train:
            return Check(
                name="Water window",
                status=Status.FAIL,
                summary=(
                    f"peak {result.peak_potential_V:+.2f} V is inside the window, but "
                    f"{drift.net_dc_current_uA:+.4g} uA of net DC reaches the edge in "
                    f"{drift.time_to_exit_s:.4g} s -- within {train}"
                ),
                detail=result.describe(),
            )
        return Check(
            name="Water window",
            status=Status.CAUTION,
            summary=(
                f"peak {result.peak_potential_V:+.2f} V, "
                f"{result.headroom_V:.2f} V headroom, but "
                f"{drift.net_dc_current_uA:+.4g} uA of net DC reaches the edge in "
                f"{drift.time_to_exit_s:.4g} s -- after {train}"
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

    Over the *binding* phase, since ledger 4. A return phase of width ``W*r`` carries
    ``I*r_a/r`` through the same area, and the package compared only the leading one: with
    ``r = 0.2`` a 1000 uA protocol drives 5000 uA back and reported a bit-identical
    verdict to the symmetric case. Each phase is compared against the threshold at its own
    width, and whichever sits closer to its own threshold is the one the verdict is about.
    """
    comparison = result.binding_threshold
    if comparison is None:  # pragma: no cover - evaluate() always supplies one
        return Check(
            name="Current density",
            status=Status.NOT_EVALUATED,
            summary=f"{result.average_A_per_cm2:.4g} A/cm^2, no threshold available",
            detail=result.describe(),
        )
    phase = (
        "" if result.binding_phase == "leading" else f" ({result.binding_phase} phase)"
    )
    if comparison.exceeds:
        return Check(
            name="Current density",
            status=Status.FAIL,
            summary=(
                f"{comparison.applied_A_per_cm2:.4g} A/cm^2{phase} is at or above the "
                f"{format_limit(comparison.threshold_A_per_cm2)} A/cm^2 electroporation threshold"
            ),
            detail=result.describe(),
            margin=comparison.margin,
        )
    return Check(
        name="Current density",
        status=Status.CAUTION if comparison.margin < CAUTION_MARGIN else Status.PASS,
        summary=(
            f"{comparison.applied_A_per_cm2:.4g} A/cm^2{phase} of the "
            f"{format_limit(comparison.threshold_A_per_cm2)} A/cm^2 electroporation threshold "
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


def _charge_balance_check(protocol: StimProtocol, area_cm2: float) -> Check:
    """State the imbalance categorically. No ceiling, and never an amplitude.

    This check bears no limit (:data:`LIMIT_BEARING`), and that is load bearing rather
    than tidy: ``unsafe_at_any_amplitude`` is defined as a FAIL from a check whose verdict
    cannot move with amplitude, so a verdict here that *did* move with amplitude would
    make ledger 84's repair report the wrong thing one phase after it landed. Everything
    said here is therefore a property of the waveform: the fraction of charge recovered,
    the resulting DC, and its density.

    **Where the consequence goes instead.** Whether a given imbalance is damaging depends
    on the electrode area, the interfacial capacitance and how long the train runs -- and
    at a small enough amplitude any partial recovery is harmless, which is precisely an
    amplitude dependence. That is the DC-drift model on the water-window check, which is
    limit-bearing and can express it as a ceiling (fix plan D6, C2.3).

    So the FAIL here is reserved for a waveform that recovers *nothing*. That is not a
    statement about the size of the DC: it is that no charge-density limit in this package
    was measured on such a waveform (Merrill et al. 2005), so none of the other checks
    means what it says. A biphasic pulse with ``charge_recovery_ratio = 0`` is that
    waveform whatever the field is called, so it is judged the same way as a monophasic
    one rather than by its spelling.
    """
    dc_density_A_per_cm2 = protocol.net_dc_current_uA * 1e-6 / area_cm2
    if protocol.return_charge_uC == 0.0:
        recovers_nothing = (
            "monophasic waveform"
            if protocol.waveform == "monophasic"
            else "return phase recovers no charge"
        )
        return Check(
            name="Charge balance",
            status=Status.FAIL,
            summary=(
                f"{recovers_nothing}: {protocol.net_dc_current_uA:.4g} uA net DC "
                f"({dc_density_A_per_cm2:.4g} A/cm^2)"
            ),
            detail=(
                "A waveform that recovers no charge accumulates all of it at the "
                "interface. Merrill et al. (2005) report significantly greater tissue "
                "damage from monophasic than from charge-balanced biphasic pulsing at "
                "matched charge density. No charge-density limit in this package is "
                "validated for delivery that recovers nothing, so no amplitude of this "
                "waveform is covered by the limits reported beside it."
            ),
        )
    if not protocol.is_charge_balanced:
        recovered = protocol.return_charge_uC / protocol.charge_per_phase_uC
        return Check(
            name="Charge balance",
            status=Status.CAUTION,
            summary=(
                f"{recovered * 100:.2f} % of the injected charge is recovered; "
                f"{protocol.net_charge_per_pulse_uC:.4g} uC/pulse left "
                f"-> {protocol.net_dc_current_uA:.4g} uA DC "
                f"({dc_density_A_per_cm2:.4g} A/cm^2)"
            ),
            detail=(
                "Sustained DC drives irreversible faradaic reactions and electrode "
                "dissolution regardless of the per-phase charge density.\n"
                "Stated here, not judged here: how long this offset takes to drive the "
                "interface out of its water window depends on the electrode area, the "
                "interfacial capacitance and the train duration, and falls with "
                "amplitude. That is an amplitude-dependent limit, so it is reported by "
                "the water-window check, which carries one."
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
    assumption = ""
    if not result.counter_modelled:
        # Never a bare PASS on a single-interface budget: a two-terminal pair needs more,
        # and under-estimating the requirement is the direction in which the stimulator
        # drops out of regulation silently (ledger 5, fix plan D7).
        status = Status.CAUTION
        assumption = (
            "; monopolar single-interface budget assumed -- supply counter_electrode "
            "for a two-terminal estimate"
        )
    return Check(
        name="Compliance voltage",
        status=status,
        summary=(
            f"{result.required_V:.2f} V of {result.available_V:.2f} V "
            f"({result.utilisation * 100:.0f} % used){assumption}"
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
        counter_electrode: Electrode | None = None,
        counter_separation_um: float | None = None,
    ) -> None:
        shannon_mod.validate_k(k)
        # At construction, as every other setting is (ledger 13): half a counter-electrode
        # input, or one the two-terminal budget cannot model, is refused here rather than
        # producing a voltage for a return path that was never described.
        compliance_mod.validate_counter(
            electrode, counter_electrode, counter_separation_um, measured_impedance_ohm
        )
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
        self.counter_electrode = counter_electrode
        self.counter_separation_um = counter_separation_um

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
            return_phase_current_uA=self.p.return_phase_current_uA,
            return_phase_width_us=self.p.return_phase_width_us,
            electrode=self.e,
        )
        ww_result = ww_mod.evaluate(
            self.material,
            charge_result.charge_density_uC_cm2,
            anodic_first=self.p.anodic_first,
            resting_potential_V=self.resting_potential_V,
            capacitance_uF_cm2=self.capacitance_uF_cm2,
            anodic_first_for_capacitance=self.p.anodic_first,
            # The three facts the DC-drift clause needs, and the only three: the offset,
            # the area it charges and how long it is applied for. Zero whenever Charge
            # balance calls the waveform balanced, so the two checks read one test and
            # cannot disagree about the same pulse (ledger 103).
            net_dc_current_uA=(
                0.0 if self.p.is_charge_balanced else self.p.net_dc_current_uA
            ),
            area_cm2=self.e.area_cm2,
            train_duration_s=self.p.train_duration_s,
            recovered_charge_uC=self.p.charge_per_phase_uC * self.p.recovered_fraction,
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
            counter_electrode=self.counter_electrode,
            counter_separation_um=self.counter_separation_um,
            # The headroom that caps the train offset is the Water window check's own.
            resting_potential_V=self.resting_potential_V,
        )

        counter_result = None
        counter_ceiling_uA = math.inf
        if self.counter_electrode is not None:
            counter_result = charge_mod.evaluate(
                get_material(self.counter_electrode.material),
                self.charge_uC * _counter_charge_scale(self.p),
                self.counter_electrode.area_cm2,
                self.p.pulse_width_us,
                self.policy,
                self.medium,
                not self.p.anodic_first,
            )
            counter_ceiling_uA = _counter_charge_ceiling_uA(
                counter_result, self.p, self.counter_electrode.area_cm2
            )

        raw_checks = (
            _shannon_check(
                shannon_result,
                self.k,
                self.p,
                self.e.area_cm2,
                envelope_result,
                geometry_note=shannon_mod.geometry_caveat(self.e),
            ),
            _charge_check(charge_result, self.p.waveform),
            _water_window_check(ww_result),
            _envelope_check(envelope_result),
            _current_density_check(jd_result),
            _regime_check(self.e, self.p),
            _chronic_check(self.material, charge_result.charge_density_uC_cm2),
            _charge_balance_check(self.p, self.e.area_cm2),
            _compliance_check(compliance_result),
        ) + (
            # Emitted only with a counter: without one, the Compliance check already says a
            # single-interface budget is assumed, and a NOT_EVALUATED here would mark every
            # monopolar assessment incomplete for a limit it cannot have (ledger 133).
            (_counter_charge_check(counter_result, self.p.waveform, counter_ceiling_uA),)
            if counter_result is not None
            else ()
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
            "Current density": _current_density_ceiling_uA(
                jd_result, self.p, self.e.area_cm2
            ),
            "Microelectrode charge/phase": _microelectrode_ceiling_uA(self.e, self.p),
            "Chronic degradation": _chronic_ceiling_uA(
                self.material, self.p, self.e.area_cm2
            ),
            "Compliance voltage": compliance_result.max_current_uA,
            "Counter charge injection": counter_ceiling_uA,
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
            or not envelope_result.supports_unqualified_pass
            # Fit on discs and written in area; Shannon says diameter (ledger 12).
            or bool(shannon_mod.geometry_caveat(self.e)),
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
            "Current density": jd_result.binding_threshold is not None,
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
            # The same caveats as the active electrode's limit.
            "Counter charge injection": counter_result is not None
            and (
                bool(counter_result.condition_warning)
                or bool(counter_result.policy_warning)
                or not counter_result.verified
            ),
        }
        _check_caveat_keys(caveats)
        checks = tuple(
            replace(
                check,
                ceiling_uA=ceiling,
                margin=_margin_from_ceiling(ceiling, self.p.current_uA),
                provisional=_provisional(caveats, check.name),
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
        cap_uA, cap_mechanism = self._biphasic_cap()
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
            biphasic_ceiling_uA=cap_uA,
            biphasic_mechanism=cap_mechanism,
            counter_charge=counter_result,
        )

    def _biphasic_cap(self) -> tuple[float, str | None]:
        """The limit the same electrode and protocol report as a biphasic waveform.

        A monophasic protocol is a strictly worse waveform and cannot earn a higher limit
        (ledger 2). See :attr:`SafetyAssessment.biphasic_ceiling_uA` for why the cap is
        needed at all.

        The counterpart is built with ``copy.copy`` and one attribute replaced, rather than
        by re-running ``__init__`` with every argument named. Enumerating the constructor a
        second time is how an argument gets silently left at its default one phase later --
        the failure mode ``tests/oracles/fail_ceiling.ConstructorDrift`` exists to catch --
        and a shallow copy carries every field that exists, including ones added after this
        line is written. The validation ``__init__`` performs was already passed by ``self``
        and none of it reads the waveform.

        Returns ``inf`` when there is no counterpart to compare against: a biphasic
        protocol is its own answer, and a monophasic one whose return phase would no longer
        fit the period has no biphasic twin at all -- ``StimProtocol`` refuses to build it,
        and a fabricated cap would be worse than none.

        Recurses exactly once: the twin is biphasic, so its own call returns immediately.
        """
        if self.p.waveform != "monophasic":
            return math.inf, None
        try:
            counterpart = replace(self.p, waveform="biphasic")
        except ValueError:
            return math.inf, None
        twin = copy.copy(self)
        twin.p = counterpart
        assessment = twin.assess()
        return assessment.limit_bearing_ceiling_uA, assessment.limiting_mechanism

    def report(self) -> dict:
        """Flat dictionary of results.

        The six keys returned by the 0.1.0 prototype are preserved with the same
        meanings; everything else is additive.
        """
        assessment = self.assess()
        unsafe = assessment.no_safe_amplitude_note()
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
            # what becomes the columns of a batch CSV (ledger 84). The conditional used to
            # live here; it now lives in the attribute, so this cannot disagree with it.
            "limiting_current_uA": assessment.limiting_current_uA,
            "limiting_mechanism": unsafe or assessment.limiting_mechanism,
            "status": assessment.status.value,
        }

    def describe(self) -> str:
        """Full human-readable assessment."""
        return self.assess().describe()
