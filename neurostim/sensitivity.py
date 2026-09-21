"""Which input actually decides the answer.

Every limit this package reports rests on a handful of choices -- the Shannon ``k``, the
end of a published charge-injection range, the tissue conductivity, whether the saline
limit is derated for in vivo use. Some of those move the answer by a factor of ten and
some barely at all, and it is not obvious in advance which is which.

This module varies each one over its defensible range while holding the rest fixed, and
reports how far the binding current limit moves. The output is a ranking: fix the top
entry by measurement and you have removed most of the uncertainty; arguing about the
bottom one is wasted effort.

A note on what the ranges mean
------------------------------
These are not error bars. Each range is the span of *defensible choices* a user could
make -- the published k band, the measured CIC interval, the spread between three
sourced conductivity values. A wide result means the literature genuinely does not pin
the answer down, which is a fact about the field rather than a defect in the calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from .data import cogan2016, gabriel1996
from .models import field as field_mod
from .safety import shannon

if TYPE_CHECKING:  # pragma: no cover
    from .safety.assessment import SafetyCalculator


@dataclass(frozen=True)
class Sensitivity:
    """How far one input moves the binding current limit."""

    parameter: str
    low_value: str
    high_value: str
    low_limit_uA: float
    high_limit_uA: float
    rationale: str

    @property
    def fold(self) -> float:
        """Ratio of the largest to smallest limit this input produces."""
        lo, hi = sorted((self.low_limit_uA, self.high_limit_uA))
        return float("inf") if lo <= 0 else hi / lo

    @property
    def dominates(self) -> bool:
        """Whether this input alone changes the answer more than twofold."""
        return self.fold > 2.0

    def describe(self) -> str:
        """One-line rendering."""
        return (
            f"{self.parameter:26s} {self.fold:5.2f}x   "
            f"{self.low_value} -> {self.low_limit_uA:.4g} uA, "
            f"{self.high_value} -> {self.high_limit_uA:.4g} uA"
        )


def _limit(
    calc: SafetyCalculator,
    *,
    k: float | None = None,
    policy: str | None = None,
    medium: str | None = None,
    tissue_conductivity_S_per_m: float | None = None,
) -> float:
    """Binding current limit with one setting replaced, everything else held fixed."""
    from .materials import Policy
    from .safety.assessment import SafetyCalculator as Calc

    varied = Calc(
        calc.e,
        calc.p,
        k=calc.k if k is None else k,
        material=calc.material,
        policy=cast("Policy", calc.policy if policy is None else policy),
        medium=calc.medium if medium is None else medium,
        tissue_conductivity_S_per_m=(
            calc.tissue_conductivity_S_per_m
            if tissue_conductivity_S_per_m is None
            else tissue_conductivity_S_per_m
        ),
        lead_resistance_ohm=calc.lead_resistance_ohm,
        compliance_V=calc.compliance_V,
        measured_impedance_ohm=calc.measured_impedance_ohm,
        resting_potential_V=calc.resting_potential_V,
        capacitance_uF_cm2=calc.capacitance_uF_cm2,
    )
    return varied.assess().limiting_current_uA


def analyse(calc: SafetyCalculator) -> list[Sensitivity]:
    """Rank the inputs by how much each moves the binding current limit."""
    results: list[Sensitivity] = []

    results.append(
        Sensitivity(
            parameter="Shannon k",
            low_value=f"{shannon.K_SHANNON:g}",
            high_value=f"{shannon.K_DAMAGE_OBSERVED:g}",
            low_limit_uA=_limit(calc, k=shannon.K_SHANNON),
            high_limit_uA=_limit(calc, k=shannon.K_DAMAGE_OBSERVED),
            rationale=(
                "Shannon's recommended line against the value at which he reports "
                "damage was observed"
            ),
        )
    )

    results.append(
        Sensitivity(
            parameter="CIC policy",
            low_value="conservative",
            high_value="optimistic",
            low_limit_uA=_limit(calc, policy="conservative"),
            high_limit_uA=_limit(calc, policy="optimistic"),
            rationale="the two ends of the published charge-injection range",
        )
    )

    results.append(
        Sensitivity(
            parameter="medium",
            low_value="in_vivo",
            high_value="saline",
            low_limit_uA=_limit(calc, medium="in_vivo"),
            high_limit_uA=_limit(calc, medium="saline"),
            rationale=(
                "published limits are saline measurements; in vivo capacity is reported "
                "as much lower"
            ),
        )
    )

    gabriel_sigma = gabriel1996.conductivity_for_pulse(calc.p.pulse_width_us)
    results.append(
        Sensitivity(
            parameter="tissue conductivity",
            low_value=f"{gabriel_sigma:.3f} S/m (Gabriel)",
            high_value=f"{field_mod.GREY_MATTER_CONDUCTIVITY_S_PER_M:g} S/m (IT'IS)",
            low_limit_uA=_limit(calc, tissue_conductivity_S_per_m=gabriel_sigma),
            high_limit_uA=_limit(
                calc,
                tissue_conductivity_S_per_m=field_mod.GREY_MATTER_CONDUCTIVITY_S_PER_M,
            ),
            rationale=(
                "three sourced values span a factor of four; only affects the answer "
                "when compliance voltage is the binding constraint"
            ),
        )
    )

    return sorted(results, key=lambda s: s.fold, reverse=True)


def describe(calc: SafetyCalculator) -> str:
    """Ranked sensitivity report."""
    rows = analyse(calc)
    lines = [
        "Sensitivity of the binding current limit to each defensible choice",
        f"  baseline: {calc.assess().limiting_current_uA:.4g} uA "
        f"({calc.assess().limiting_mechanism})",
        "",
    ]
    lines += [f"  {row.describe()}" for row in rows]
    dominant = [r for r in rows if r.dominates]
    lines.append("")
    if dominant:
        lines.append(
            "  Dominant: "
            + ", ".join(r.parameter for r in dominant)
            + ".\n  Measuring these on your own electrodes removes most of the spread; "
            "the rest\n  is not worth arguing about."
        )
    else:
        lines.append(
            "  No single choice moves the answer more than twofold: the limit is robust "
            "to\n  every defensible setting here."
        )
    lines.append(
        "\n  These are ranges of defensible choices, not error bars. A wide result means "
        "the\n  literature does not pin the answer down."
    )
    return "\n".join(lines)


def in_vivo_note(calc: SafetyCalculator) -> str:
    """The reported in vivo derating for this material, or a note that none exists."""
    derating = cogan2016.derating_for(calc.material.key)
    if derating is None:
        return f"No in vivo derating reported for {calc.material.key}."
    return f"{calc.material.key}: {derating.describe()}"
