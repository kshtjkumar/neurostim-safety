"""Charge density and the material charge-injection capacity (CIC) limit.

The CIC is the maximum charge density a material can inject before the electrode
potential leaves the water window, i.e. before further injected charge necessarily
drives irreversible water electrolysis. It is a property of the *electrode*, whereas
the Shannon criterion is a property of the *tissue*. Both must hold; neither implies
the other.

No pulse-width scaling law is applied. Published CIC values are measured at a specific
pulse width and the dependence is material- and film-specific -- Cogan (2008) reports
sputtered iridium oxide limits that differ several-fold between sub-millisecond and
10 ms pulsing. Rather than invent a correction, this module reports the measurement
conditions alongside the limit and raises a caution when the protocol is far from them.

**Not applied to monophasic delivery** (ledger 2, C2.4). Every CIC in this database was
measured with a charge-balanced biphasic waveform (Merrill et al. 2005), and a CIC is the
density reachable *given that the return phase recovers it*. For delivery that recovers
nothing, the assessment reports the Charge injection check as NOT_EVALUATED and sets
``limits_incomplete``, rather than borrowing a number measured on a different waveform.
:func:`evaluate` still computes the biphasic figure. The refusal is made in
``assessment._charge_check``, which knows the waveform. What replaces this limit for a
monophasic protocol is the water window's DC-drift clause and the cap at the biphasic
twin's limit (``SafetyAssessment.biphasic_ceiling_uA``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..data import cogan2016
from ..materials import Material, Policy, get_material
from ..uncertainty import Interval
from ..units import charge_uC
from ._limits import floor_to_pass, format_limit

PULSE_WIDTH_TOLERANCE = 2.0
"""Fold-difference in pulse width beyond which the CIC condition mismatch is flagged."""


def charge_density_uC_cm2(charge_per_phase_uC: float, area_cm2: float) -> float:
    """Charge density per phase.

    Raises
    ------
    ValueError
        If ``area_cm2`` is not positive and finite.
    """
    if not math.isfinite(area_cm2) or area_cm2 <= 0:
        raise ValueError(f"area_cm2 must be finite and > 0, got {area_cm2!r}")
    if not math.isfinite(charge_per_phase_uC):
        raise ValueError(
            f"charge_per_phase_uC must be finite, got {charge_per_phase_uC!r}"
        )
    return charge_per_phase_uC / area_cm2


def cic_max_charge_uC(
    material: Material | str,
    area_cm2: float,
    policy: Policy = "conservative",
    anodic_first: bool | None = None,
) -> float:
    """Maximum charge per phase the material supports over the given area."""
    mat = material if isinstance(material, Material) else get_material(material)
    if not math.isfinite(area_cm2) or area_cm2 <= 0:
        raise ValueError(f"area_cm2 must be finite and > 0, got {area_cm2!r}")
    return mat.cic_uC_cm2(policy, anodic_first) * area_cm2


def cic_max_current_uA(
    material: Material | str,
    area_cm2: float,
    pulse_width_us: float,
    policy: Policy = "conservative",
    anodic_first: bool | None = None,
) -> float:
    """Maximum leading-phase current the material supports.

    Settled onto the boundary of the forward check (ledger 9). This is a *second*
    back-solve, separate from the one :func:`evaluate` performs and reached through
    ``SafetyCalculator.max_current_cic_uA``, so it sits behind every batch CSV row and the
    amplitude-limits figure. Flooring it here is what keeps the two agreeing; a test
    asserts they do.
    """
    if not math.isfinite(pulse_width_us) or pulse_width_us <= 0:
        raise ValueError(
            f"pulse_width_us must be finite and > 0, got {pulse_width_us!r}"
        )
    mat = material if isinstance(material, Material) else get_material(material)
    limit = mat.cic_uC_cm2(policy, anodic_first)
    return floor_to_pass(
        cic_max_charge_uC(mat, area_cm2, policy, anodic_first) / (pulse_width_us * 1e-6),
        lambda current_uA: charge_density_uC_cm2(
            charge_uC(current_uA, pulse_width_us), area_cm2
        )
        <= limit,
        name="Charge injection limit",
    )


def _max_current_uA(limit_uC_cm2: float, area_cm2: float, pulse_width_us: float) -> float:
    """Largest amplitude whose charge density stays at or below ``limit_uC_cm2``."""
    return floor_to_pass(
        (limit_uC_cm2 * area_cm2) / (pulse_width_us * 1e-6),
        lambda current_uA: charge_density_uC_cm2(
            charge_uC(current_uA, pulse_width_us), area_cm2
        )
        <= limit_uC_cm2,
        name="Charge injection limit",
    )


@dataclass(frozen=True)
class ChargeResult:
    """Outcome of the material charge-injection check."""

    material_key: str
    charge_per_phase_uC: float
    charge_density_uC_cm2: float
    cic_limit_uC_cm2: float
    max_charge_uC: float
    max_current_uA: float
    policy: str
    polarity: str
    conditions: str
    verified: bool
    condition_warning: str = ""
    policy_warning: str = ""
    """Set when the selected policy is more permissive than the source endorses.

    Kept separate from ``condition_warning`` because it is a different kind of problem:
    the conditions warning says the limit may not transfer to your protocol, this one
    says the limit is not the one the cited work stands behind.
    """
    limit_interval_uC_cm2: Interval | None = None
    max_current_interval_uA: Interval | None = None
    medium: str = "saline"
    derating_applied: float = 1.0
    derating_note: str = ""

    @property
    def limit_is_a_range(self) -> bool:
        """Whether the published limit spans a range rather than a single value."""
        return (
            self.limit_interval_uC_cm2 is not None
            and not self.limit_interval_uC_cm2.is_exact
        )

    @property
    def passes(self) -> bool:
        """Whether the applied charge density is at or below the material limit."""
        return self.charge_density_uC_cm2 <= self.cic_limit_uC_cm2

    @property
    def utilisation(self) -> float:
        """Applied charge density as a fraction of the limit; 1.0 is exactly at it."""
        return self.charge_density_uC_cm2 / self.cic_limit_uC_cm2

    @property
    def margin(self) -> float:
        """Ratio of the permitted charge density to the applied one."""
        if self.charge_density_uC_cm2 <= 0:
            return math.inf
        return self.cic_limit_uC_cm2 / self.charge_density_uC_cm2

    def describe(self) -> str:
        """Multi-line summary."""
        verdict = "PASS" if self.passes else "EXCEEDS"
        lines = [
            f"Charge injection ({self.material_key}, {self.policy}, "
            f"{self.polarity}) -> {verdict}",
            f"  applied   {self.charge_density_uC_cm2:.4g} uC/cm^2",
            f"  limit     {format_limit(self.cic_limit_uC_cm2)} uC/cm^2 "
            f"({self.utilisation * 100:.1f} % used)",
            f"  max current {format_limit(self.max_current_uA)} uA",
        ]
        if self.limit_is_a_range:
            assert self.limit_interval_uC_cm2 is not None
            assert self.max_current_interval_uA is not None
            # Both ends are limits, so both floor -- the same reason the uA interval
            # beside them does. This line used to render them with `:.4g` by hand, which
            # printed 7.143 for a low end of 7.142857142857143 (ledger 96).
            lines.append(
                f"  published range "
                f"{self.limit_interval_uC_cm2.describe('uC/cm^2', floor=True)} "
                f"({self.limit_interval_uC_cm2.fold_range:.1f}x) "
                f"-> {self.max_current_interval_uA.describe('uA', floor=True)}"
            )
        if self.derating_applied != 1.0:
            lines.append(
                f"  IN VIVO: saline limit divided by {self.derating_applied:g}x "
                f"-- {self.derating_note}"
            )
        elif self.medium == "in_vivo" and self.derating_note:
            lines.append(f"  IN VIVO: {self.derating_note}")
        lines.append(f"  measured under: {self.conditions}")
        lines.append(
            "  note: this is a geometric-average density. On a non-recessed electrode "
            "the\n  local peak at the perimeter is higher -- Kuncel & Grill (2004) "
            "found 25.6 % of a\n  DBS contact above its average current density."
        )
        if not self.verified:
            lines.append("  PROVISIONAL: limit not confirmed against a primary source")
        if self.condition_warning:
            lines.append(f"  CAUTION: {self.condition_warning}")
        if self.policy_warning:
            lines.append(f"  POLICY: {self.policy_warning}")
        return "\n".join(lines)


def evaluate(
    material: Material | str,
    charge_per_phase_uC: float,
    area_cm2: float,
    pulse_width_us: float,
    policy: Policy = "conservative",
    medium: str = "saline",
    anodic_first: bool | None = None,
) -> ChargeResult:
    """Evaluate the charge-injection limit and flag condition mismatches.

    ``medium`` selects whether the published saline limit is used as-is
    (``"saline"``, the default) or divided by the reported in vivo reduction
    (``"in_vivo"``). Cogan et al. (2016) report the apparent in vivo charge-injection
    capacity as up to tenfold below the saline value for platinum and activated iridium
    oxide, and fourfold for SIROF. Applying that derating is a choice with large
    consequences, so it is opt-in and always labelled in the output.
    """
    if medium not in ("saline", "in_vivo"):
        raise ValueError(
            f"medium must be 'saline' or 'in_vivo', got {medium!r}"
        )
    mat = material if isinstance(material, Material) else get_material(material)
    density = charge_density_uC_cm2(charge_per_phase_uC, area_cm2)
    limit = mat.cic_uC_cm2(policy, anodic_first)

    derating = 1.0
    derating_note = ""
    if medium == "in_vivo":
        reported = cogan2016.derating_for(mat.key)
        if reported is None:
            derating_note = (
                f"no in vivo derating is reported for {mat.key}; the saline limit is "
                f"used unchanged and is likely optimistic"
            )
        else:
            derating = reported.worst
            derating_note = reported.describe()
            limit = limit / derating

    warning = ""
    measured_pw = mat.cic.pulse_width_us
    if measured_pw is None:
        warning = (
            f"the cited limit for {mat.key} carries no stated pulse width, so its "
            f"applicability at {pulse_width_us:g} us is unknown"
        )
    else:
        fold = max(pulse_width_us / measured_pw, measured_pw / pulse_width_us)
        if fold > PULSE_WIDTH_TOLERANCE:
            direction = "longer" if pulse_width_us > measured_pw else "shorter"
            warning = (
                f"protocol pulse width {pulse_width_us:g} us is {fold:.1f}x {direction} "
                f"than the {measured_pw:g} us at which this limit was measured; "
                f"charge-injection capacity is pulse-width dependent and no scaling "
                f"has been applied"
            )

    scale = 1e3 if mat.cic.units == "mC/cm2" else 1.0
    bound_low, bound_high = mat.cic.bounds(anodic_first)
    policy_warning = ""
    # Bound to a local so the type narrows: exceeds_recommendation() is only ever True
    # when recommended_policy is set, but that is not visible to a type checker.
    endorsed_policy = mat.cic.recommended_policy
    if endorsed_policy is not None and mat.cic.exceeds_recommendation(policy):
        endorsed = mat.cic_uC_cm2(endorsed_policy, anodic_first)
        # Both are maxima, and `limit` may be derated or a midpoint -- round only by
        # accident, so `:g` would print it high (ledger 100).
        policy_warning = (
            f"the '{policy}' policy applies {format_limit(limit)} uC/cm^2, but the source "
            f"for this limit endorses the '{endorsed_policy}' end at "
            f"{format_limit(endorsed)} uC/cm^2"
        )
        if mat.cic.recommendation_note:
            policy_warning += f" -- {mat.cic.recommendation_note}"

    limit_interval = Interval(
        bound_low * scale / derating, bound_high * scale / derating
    )
    # Each end floored through the point's own predicate (ledger 136). The closed form
    # ``limit * A / W`` can sit an ulp or two below the float boundary the point is settled
    # onto, and then the point fell outside its own interval. The ends' limits are formed
    # by the same operations as the point's, so they bracket it, and the boundary is
    # monotone in the limit.
    current_interval = Interval(
        _max_current_uA(limit_interval.low, area_cm2, pulse_width_us),
        _max_current_uA(limit_interval.high, area_cm2, pulse_width_us),
    )

    return ChargeResult(
        material_key=mat.key,
        charge_per_phase_uC=charge_per_phase_uC,
        charge_density_uC_cm2=density,
        cic_limit_uC_cm2=limit,
        max_charge_uC=floor_to_pass(
            limit * area_cm2,
            lambda charge_uC_: charge_density_uC_cm2(charge_uC_, area_cm2) <= limit,
            name="Charge injection limit",
        ),
        # Floored against this result's own forward comparison -- `density <= limit`,
        # with the same `limit` the derating and policy above produced, not the material's
        # raw value. See _limits.floor_to_pass and ledger 9.
        max_current_uA=_max_current_uA(limit, area_cm2, pulse_width_us),
        policy=policy,
        polarity=(
            "unspecified"
            if anodic_first is None
            else ("anodic-first" if anodic_first else "cathodic-first")
        ),
        conditions=mat.cic.describe(),
        verified=mat.cic.verified,
        condition_warning=warning,
        policy_warning=policy_warning,
        limit_interval_uC_cm2=limit_interval,
        max_current_interval_uA=current_interval,
        medium=medium,
        derating_applied=derating,
        derating_note=derating_note,
    )
