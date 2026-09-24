"""Literature-backed electrode material database.

Every number here was read out of the primary source text listed in
:mod:`neurostim.references` and carries its measurement conditions. This matters more
than it might appear: a charge-injection limit is **not** a material constant. It
depends on pulse width, waveform polarity, interpulse bias, electrolyte, and whether
the area used to normalise it was geometric or real (roughness-corrected) surface area.
Quoting a single scalar per material -- as most calculators do -- silently discards all
of that.

Values whose ``verified`` flag is ``False`` were not confirmed against a primary source
and are surfaced as ``PROVISIONAL`` everywhere they are used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

from .references import cite

BODY_TEMPERATURE_C = 37.0
"""Temperature at which a stimulating electrode actually operates."""

AIROF_TEMPERATURE_GAIN = 2.0 / 1.67
"""Charge-injection gain from 20 C to 37 C measured on AIROF at 0.1 ms.

Cogan (2008): Qinj rose from 1.67 to 2.0 mC/cm^2 between 20 C and 37 C, with access
resistance falling from 5360 to 4052 ohm over the same interval. Cogan notes porous and
multilayer films -- iridium oxide and porous TiN -- are the most temperature sensitive
because their charge injection is transport limited.

Applied nowhere automatically: it was measured on one film at one pulse width, and
extrapolating it to other materials is not supported. It is exposed so a
room-temperature literature value can be recognised as conservative rather than exact.
"""

AreaBasis = Literal["geometric", "real", "unspecified"]
Mechanism = Literal["capacitive", "faradaic", "faradaic/capacitive"]
Policy = Literal["conservative", "nominal", "optimistic"]


def _check_bounds(
    owner: str, label: str, low: float, high: float, *, reference: str
) -> None:
    """Refuse a range whose bounds are not positive finite numbers in order (ledger 24)."""
    for name, value in (("low", low), ("high", high)):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                f"{owner} {label} {name} bound must be a finite number > 0, got {value!r} "
                f"(reference {reference!r})"
            )
    if high < low:
        raise ValueError(
            f"{owner} {label} high ({high}) < low ({low}) for reference {reference!r}"
        )


@dataclass(frozen=True)
class MeasuredRange:
    """A literature value with its measurement conditions and provenance.

    ``low``/``high`` bracket the reported range. Where a source reports a single
    approximate value (Cogan 2008 writes "~1"), ``low == high`` and ``approximate`` is
    set so reports can render it as "~".
    """

    low: float
    high: float
    units: str
    reference: str
    verified: bool = True
    approximate: bool = False
    pulse_width_us: float | None = None
    waveform: str = ""
    bias: str = ""
    medium: str = ""
    area_basis: AreaBasis = "unspecified"
    temperature_C: float | None = None
    measured_area_cm2: float | None = None
    recommended_policy: Policy | None = None
    """Which end of the range the primary source itself endorses, where it takes a view.

    Most sources report a range without arguing for either end, and this stays ``None``.
    Some do argue: Riedy & Walter's paper exists to talk the 40 uC/cm^2 stainless-steel
    recommendation *down* to 20, on the grounds that the higher figure rests on a
    one-hour pulsing study. Selecting the optimistic end there does not pick a
    defensible extreme of a measured range -- it applies a number the cited work was
    written to dispute, and nothing said so.
    """
    recommendation_note: str = ""
    """Why the source prefers that end. Shown wherever the recommendation is exceeded."""
    anodic_first_range: tuple[float, float] | None = None
    """Sub-range measured with anodic-first pulsing, if the source resolved it."""
    cathodic_first_range: tuple[float, float] | None = None
    """Sub-range measured with cathodic-first pulsing, if the source resolved it."""
    note: str = ""

    def __post_init__(self) -> None:
        # Each bound must be a positive finite number (ledger 24). ``high < low`` alone is
        # False for NaN, so a NaN bound constructed and every policy that read it returned
        # nan; inf and non-positive bounds passed too.
        ranges = {
            "range": (self.low, self.high),
            "anodic-first range": self.anodic_first_range,
            "cathodic-first range": self.cathodic_first_range,
        }
        for label, bounds in ranges.items():
            if bounds is not None:
                _check_bounds("MeasuredRange", label, *bounds, reference=self.reference)
        cite(self.reference)  # fail loudly on an unknown citation key

    @property
    def peer_reviewed(self) -> bool:
        """Whether the value's source went through peer review."""
        return cite(self.reference).peer_reviewed

    @property
    def measured_below_body_temperature(self) -> bool:
        """Whether the value was measured cold enough to understate in-body capacity.

        ``None`` temperature counts as unknown, not as body temperature.
        """
        return (
            self.temperature_C is not None
            and self.temperature_C < BODY_TEMPERATURE_C - 2.0
        )

    def bounds(self, anodic_first: bool | None = None) -> tuple[float, float]:
        """Range for a pulse polarity, narrowing to a sub-range where one was measured.

        Rose & Robblee (1990) resolved platinum into 50-100 uC/cm^2 anodic-first and
        100-150 uC/cm^2 cathodic-first. Quoting the union of the two, 50-150, is both
        too permissive for anodic-first pulsing and needlessly strict for cathodic-first.
        Passing the protocol's polarity selects the range that was actually measured.
        """
        if anodic_first is True and self.anodic_first_range is not None:
            return self.anodic_first_range
        if anodic_first is False and self.cathodic_first_range is not None:
            return self.cathodic_first_range
        return (self.low, self.high)

    def value(
        self, policy: Policy = "conservative", anodic_first: bool | None = None
    ) -> float:
        """Collapse the range to a single number under an explicit policy.

        ``conservative`` returns the low end (the default everywhere in this package),
        ``optimistic`` the high end, ``nominal`` the midpoint. ``anodic_first`` narrows
        to a polarity-specific sub-range where the source measured one.
        """
        low, high = self.bounds(anodic_first)
        if policy == "conservative":
            return low
        if policy == "optimistic":
            return high
        if policy == "nominal":
            return 0.5 * (low + high)
        raise ValueError(
            f"Unknown policy {policy!r}; expected conservative/nominal/optimistic"
        )

    def exceeds_recommendation(self, policy: Policy) -> bool:
        """Whether ``policy`` is more permissive than the source itself endorses.

        Permissiveness runs conservative < nominal < optimistic. Returns ``False`` when
        the source took no position, which is the usual case.
        """
        if self.recommended_policy is None:
            return False
        order = {"conservative": 0, "nominal": 1, "optimistic": 2}
        return order[policy] > order[self.recommended_policy]

    @property
    def is_range(self) -> bool:
        """True when the source reported an interval rather than a point value."""
        return self.high > self.low

    def describe(self) -> str:
        """Human-readable value with units, range markers and provenance flag."""
        prefix = "~" if self.approximate and not self.is_range else ""
        body = (
            f"{self.low:g}-{self.high:g}" if self.is_range else f"{prefix}{self.low:g}"
        )
        text = f"{body} {self.units}"
        conditions = []
        if self.pulse_width_us is not None:
            conditions.append(f"{self.pulse_width_us:g} us")
        if self.waveform:
            conditions.append(self.waveform)
        if self.bias:
            conditions.append(self.bias)
        if self.temperature_C is not None:
            marker = " (below body temperature)" if self.measured_below_body_temperature else ""
            conditions.append(f"{self.temperature_C:g} C{marker}")
        if self.measured_area_cm2 is not None:
            conditions.append(f"on {self.measured_area_cm2:.3g} cm^2")
        if self.area_basis != "unspecified":
            conditions.append(f"{self.area_basis} area")
        if conditions:
            text += f" [{', '.join(conditions)}]"
        if not self.peer_reviewed and self.reference != "user_measurement":
            text += " NOT PEER REVIEWED"
        if self.reference == "user_measurement":
            text += " (your measurement, not published literature)"
            if self.note:
                text += f" -- {self.note}"
        else:
            text += f" ({self.reference})"
        if not self.verified:
            text += " PROVISIONAL"
        return text


@dataclass(frozen=True)
class WaterWindow:
    """Cathodic and anodic potential limits, in volts versus an Ag|AgCl reference.

    Outside this window all further injected charge drives irreversible water reduction
    (hydrogen evolution, cathodic) or oxidation (oxygen evolution, anodic).
    """

    cathodic_V: float
    anodic_V: float
    reference: str
    verified: bool = True
    scale: str = "vs Ag|AgCl"
    """What the limits are measured against.

    Defaults to the conventional Ag|AgCl restatement. Set it when the bounds are
    something else -- 316LVM's are a polarisation magnitude relative to the resting
    potential, not an absolute potential on any reference scale, and rendering those as
    "vs Ag|AgCl" would misstate them.
    """
    note: str = ""
    inherited_from: str = ""
    """The material this value was published for, when it is carried onto a user material.

    Set by :func:`with_measured_cic` on the constants it keeps (ledger 25): the value and
    its reference are the base material's, and every render says so rather than
    presenting them as the user material's own. Empty for a value published for this
    material.
    """

    def __post_init__(self) -> None:
        if self.cathodic_V >= self.anodic_V:
            raise ValueError(
                f"WaterWindow cathodic limit ({self.cathodic_V} V) must be below the "
                f"anodic limit ({self.anodic_V} V) for reference {self.reference!r}"
            )
        cite(self.reference)

    @property
    def width_V(self) -> float:
        """Total width of the window in volts."""
        return self.anodic_V - self.cathodic_V

    def contains(self, potential_V: float) -> bool:
        """Whether an electrode potential lies inside the window."""
        return self.cathodic_V <= potential_V <= self.anodic_V

    def describe(self) -> str:
        """Human-readable window with provenance flag."""
        text = f"{self.cathodic_V:+g} to {self.anodic_V:+g} V {self.scale}"
        text += (
            f", {inherited_label(self.inherited_from, self.reference)}"
            if self.inherited_from
            else f" ({self.reference})"
        )
        if not self.verified:
            text += " PROVISIONAL"
        return text


@dataclass(frozen=True)
class ChronicThreshold:
    """A degradation threshold that sits *below* the charge-injection limit.

    The charge-injection limit answers "will the interface stay inside the water
    window for this pulse". It does not answer "will this electrode survive months of
    pulsing, and will what it sheds harm the tissue". For platinum those are different
    numbers and the second is several times lower, so a protocol can be comfortably
    inside its CIC and still erode the electrode.
    """

    low_uC_cm2: float
    high_uC_cm2: float
    mechanism: str
    reference: str
    note: str = ""
    verified: bool = True
    """Whether the threshold is confirmed against its primary source (ledger 30).

    Rolls into :attr:`Material.verified` beside the CIC's and the water window's flags;
    it had no flag at all, so an unconfirmed threshold could not say so.
    """
    inherited_from: str = ""
    """The material this value was published for, when it is carried onto a user material.

    Set by :func:`with_measured_cic` on the constants it keeps (ledger 25): the value and
    its reference are the base material's, and every render says so rather than
    presenting them as the user material's own. Empty for a value published for this
    material.
    """

    def __post_init__(self) -> None:
        _check_bounds(
            "ChronicThreshold", "band", self.low_uC_cm2, self.high_uC_cm2,
            reference=self.reference,
        )
        cite(self.reference)

    def describe(self) -> str:
        """Human-readable threshold with provenance."""
        body = (
            f"{self.low_uC_cm2:g}-{self.high_uC_cm2:g}"
            if self.high_uC_cm2 > self.low_uC_cm2
            else f"{self.low_uC_cm2:g}"
        )
        text = (
            f"{body} uC/cm^2 ({self.mechanism}), "
            f"{inherited_label(self.inherited_from, self.reference)}"
            if self.inherited_from
            else f"{body} uC/cm^2 ({self.mechanism}, {self.reference})"
        )
        if not self.verified:
            text += " PROVISIONAL"
        if self.note:
            text += f" -- {self.note}"
        return text


@dataclass(frozen=True)
class Material:
    """An electrode material with its charge-injection limit and water window."""

    key: str
    name: str
    mechanism: Mechanism
    cic: MeasuredRange
    water_window: WaterWindow | None = None
    chronic_threshold: ChronicThreshold | None = None
    aliases: tuple[str, ...] = ()
    note: str = ""
    dropped: tuple[str, ...] = ()
    """Published constants the user dropped from a :func:`with_measured_cic` material.

    ``"water window"`` or ``"chronic threshold"``. The check that needed the constant does
    not run, and says why, as does the assessment's incomplete-limits note (ledger 25).
    """

    @property
    def verified(self) -> bool:
        """True only when every constant attached to this material is primary-sourced."""
        ww_ok = self.water_window is None or self.water_window.verified
        chronic_ok = self.chronic_threshold is None or self.chronic_threshold.verified
        return self.cic.verified and ww_ok and chronic_ok

    def cic_uC_cm2(
        self, policy: Policy = "conservative", anodic_first: bool | None = None
    ) -> float:
        """Charge-injection limit in uC/cm^2 under the given policy and polarity."""
        value = self.cic.value(policy, anodic_first)
        if self.cic.units == "mC/cm2":
            return value * 1e3
        if self.cic.units == "uC/cm2":
            return value
        raise ValueError(f"Unhandled CIC units {self.cic.units!r} for {self.key}")

    def describe(self) -> str:
        """Multi-line summary of the material record."""
        lines = [
            f"{self.name} ({self.key}) -- {self.mechanism}",
            f"  charge-injection limit: {self.cic.describe()}",
        ]
        if self.water_window is not None:
            lines.append(f"  water window:           {self.water_window.describe()}")
        else:
            lines.append("  water window:           not reported in the cited source")
        if self.note:
            lines.append(f"  note: {self.note}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------------
# The database.
#
# Cogan (2008) Table 2 "Charge-injection limits of electrode materials for stimulation
# in the CNS" is transcribed below with its potential limits. Pt is additionally
# resolved into its anodic-first / cathodic-first sub-ranges from Rose & Robblee (1990)
# as quoted in Merrill (2005) section 3, which is where Cogan's 0.05-0.15 mC/cm^2
# actually comes from.
# ---------------------------------------------------------------------------------

_PT_IR_WINDOW = WaterWindow(
    cathodic_V=-0.6,
    anodic_V=0.8,
    reference="cogan2008",
    note=(
        "Cogan 2008 Table 2, applies to Pt, PtIr and all iridium oxide variants. "
        "Reference-electrode caveat: Cogan states these versus Ag|AgCl, but both "
        "underlying primary studies measured versus SCE -- Rose & Robblee (1990) give "
        "-0.60 and +0.90 V vs SCE, Beebe & Rose (1988) give -0.6 and +0.8 V vs SCE. "
        "SCE sits about 45 mV positive of a saturated Ag|AgCl reference, so the window "
        "quoted here is the conventional restatement rather than either primary "
        "measurement. Compare against measured voltage transients on your own "
        "reference electrode's scale."
    ),
)

_MATERIAL_LIST: tuple[Material, ...] = (
    Material(
        key="Pt",
        name="Platinum",
        mechanism="faradaic/capacitive",
        aliases=("platinum",),
        cic=MeasuredRange(
            low=0.05,
            high=0.15,
            units="mC/cm2",
            reference="rose_robblee1990",
            pulse_width_us=200.0,
            waveform="charge-balanced, capacitively coupled biphasic, 50 pps",
            medium="phosphate- or bicarbonate-buffered saline, pH 7.3",
            area_basis="geometric",
            anodic_first_range=(0.05, 0.10),
            cathodic_first_range=(0.10, 0.15),
            note=(
                "Rose & Robblee (1990), read from the primary text: 50-100 uC/cm^2 "
                "anodic-first, 100-150 uC/cm^2 cathodic-first, at 0.2 ms and 50 pps. "
                "Their stated potential limits are -0.60 and +0.90 V versus SCE, not "
                "versus Ag|AgCl; Cogan 2008 restates them as -0.6 to 0.8 V vs Ag|AgCl. "
                "Two strong dependences they measured directly: raising the pulse to "
                "1 ms lifts the limit to 250 uC/cm^2 cathodic-first, and biasing the "
                "electrode to +0.9 V vs SCE lifts it to 600 uC/cm^2. Brummer & "
                "Turner's 300-350 uC/cm^2 real-area figure was measured at >0.6 ms and "
                "does not apply at neural-stimulation pulse widths."
            ),
        ),
        water_window=_PT_IR_WINDOW,
        chronic_threshold=ChronicThreshold(
            low_uC_cm2=20.0,
            high_uC_cm2=50.0,
            mechanism="platinum dissolution",
            reference="rose_robblee1990",
            note=(
                "Rose & Robblee report dissolution at 20-50 uC/cm^2 geometric, below "
                "even the conservative end of the charge-injection limit. Staying "
                "inside the water window does not prevent it"
            ),
        ),
        note=(
            "Pt dissolution rises linearly with injected charge and begins well below "
            "the charge-injection limit; anodic-first pulsing dissolves more than "
            "cathodic-first (Merrill 2005). Serum protein reduces the dissolution rate "
            "by about an order of magnitude."
        ),
    ),
    Material(
        key="PtIr",
        name="Platinum-iridium alloy",
        mechanism="faradaic/capacitive",
        aliases=("pt-ir", "ptir", "platinum iridium"),
        cic=MeasuredRange(
            low=0.05,
            high=0.15,
            units="mC/cm2",
            reference="rose_robblee1990",
            pulse_width_us=200.0,
            waveform="charge-balanced, capacitively coupled biphasic, 50 pps",
            medium="phosphate- or bicarbonate-buffered saline, pH 7.3",
            area_basis="geometric",
            anodic_first_range=(0.05, 0.10),
            cathodic_first_range=(0.10, 0.15),
            note=(
                "Cogan 2008 Table 2 reports a single row for 'Pt and PtIr alloys'. "
                "Treating PtIr as having a distinctly higher limit than Pt is not "
                "supported by that table. Cogan separately reports that PtIr-alloy "
                "microelectrodes show a strongly bias-dependent cathodal limit rising "
                "from 90 to 300 uC/cm^2 as the bias goes from 0.1 V to 0.7 V "
                "(Ag|AgCl), so a biased PtIr microelectrode can exceed this range."
            ),
        ),
        water_window=_PT_IR_WINDOW,
        chronic_threshold=ChronicThreshold(
            low_uC_cm2=20.0,
            high_uC_cm2=50.0,
            mechanism="platinum dissolution",
            reference="rose_robblee1990",
            note="Assumed to follow Pt; not measured separately for the alloy",
        ),
        note="Alloyed with Ir for mechanical stiffness; electrochemistry close to Pt.",
    ),
    Material(
        key="AIROF",
        name="Activated iridium oxide film",
        mechanism="faradaic",
        aliases=("activated iridium oxide", "airof", "iro2-activated"),
        cic=MeasuredRange(
            low=1.0,
            high=3.5,
            units="mC/cm2",
            reference="beebe_rose1988",
            pulse_width_us=200.0,
            waveform="charge-balanced biphasic, 50 pps",
            bias="+0.8 V vs SCE for the 3.5 mC/cm^2 monophasic cathodal figure",
            medium="bicarbonate buffered saline, pH 7.3, 80 ohm.cm",
            measured_area_cm2=4.1e-4,
            area_basis="geometric",
            anodic_first_range=(2.1, 2.1),
            cathodic_first_range=(1.0, 1.0),
            note=(
                "Beebe & Rose (1988) primary values on activated iridium wire, "
                "3.7-4.5e-4 cm^2: 1.0 mC/cm^2 cathodic-first and 2.1 mC/cm^2 "
                "anodic-first at 0.2 ms, rising to 3.5 mC/cm^2 with monophasic "
                "cathodal pulses on an electrode biased to +0.8 V vs SCE. Their "
                "potential limits of -0.6 and +0.8 V are versus SCE, not Ag|AgCl. "
                "They note the limits are conservative for pulsing because pH shifts "
                "and uncompensated iR drop widen the usable window. Cogan 2008 "
                "Table 2 rounds this row to 1-5 mC/cm^2. Cogan also reports Qinj "
                "rising from 1.67 to 2.0 mC/cm^2 between 20 C and 37 C at 0.1 ms, so "
                "room-temperature figures understate body-temperature performance."
            ),
        ),
        water_window=_PT_IR_WINDOW,
        note=(
            "Damaged by extreme negative potentials (< -0.6 V). The upper end of the "
            "range is only reachable with an applied positive interpulse bias."
        ),
    ),
    Material(
        key="SIROF",
        name="Sputtered iridium oxide film",
        mechanism="faradaic",
        aliases=("sputtered iridium oxide", "sirof"),
        cic=MeasuredRange(
            low=1.0,
            high=5.0,
            units="mC/cm2",
            reference="cogan2004_sirof",
            pulse_width_us=400.0,
            waveform="biphasic",
            bias="0.6 V vs Ag|AgCl interpulse bias for the high end",
            measured_area_cm2=2e-5,
            area_basis="geometric",
            note=(
                "Cogan 2008 Table 2. Strongly area dependent: about 5 mC/cm^2 on "
                "2000 um^2 electrodes (100 nC/phase) at 400 us with 0.6 V bias, but "
                "only 750 uC/cm^2 on 0.05 cm^2 electrodes at 0.75 ms, and 100 uC/cm^2 "
                "for 200 nm SIROF at 10 ms (Slavcheva et al.). Applying the high end "
                "to a macroelectrode is not supported."
            ),
        ),
        water_window=_PT_IR_WINDOW,
        note=(
            "Damaged by extreme negative potentials (< -0.6 V). Maintains higher Qinj "
            "than AIROF at potentials below 0.4 V vs Ag|AgCl."
        ),
    ),
    Material(
        key="TIROF",
        name="Thermal iridium oxide film",
        mechanism="faradaic",
        aliases=("thermal iridium oxide", "tirof"),
        cic=MeasuredRange(
            low=1.0,
            high=1.0,
            units="mC/cm2",
            reference="robblee1986_tirof",
            approximate=True,
            bias="positive bias required for high Qinj",
            note=(
                "Cogan 2008 Table 2 reports '~1', citing Robblee et al. (1986). "
                "No pulse width is stated for this row in either source."
            ),
        ),
        water_window=_PT_IR_WINDOW,
    ),
    Material(
        key="TiN",
        name="Titanium nitride",
        mechanism="capacitive",
        aliases=("titanium nitride", "tin"),
        cic=MeasuredRange(
            low=1.0,
            high=1.0,
            units="mC/cm2",
            reference="weiland2002_tin",
            approximate=True,
            pulse_width_us=500.0,
            medium="in vitro",
            measured_area_cm2=4e-5,
            area_basis="geometric",
            note=(
                "Cogan 2008 Table 2 reports '~1'. The underlying measurement is "
                "Weiland et al. (2002): 0.9 mC/cm^2 in vitro at 0.5 ms on 4000 um^2 "
                "electrodes. Higher values are possible at higher ESA/GSA ratios."
            ),
        ),
        water_window=WaterWindow(
            cathodic_V=-0.9,
            anodic_V=0.9,
            reference="cogan2008",
            note=(
                "Wider than Pt/IrOx; water reduction and oxidation at -0.9 V and 0.9 V "
                "by slow-sweep cyclic voltammetry."
            ),
        ),
        note=(
            "High ESA/GSA porous film. Access to the full charge storage capacity is "
            "limited by pore resistance at stimulation pulse rates, so the usable "
            "injection limit is well below the slow-CV charge storage capacity. "
            "Oxidised at positive potentials."
        ),
    ),
    Material(
        key="PEDOT",
        name="Poly(3,4-ethylenedioxythiophene)",
        mechanism="faradaic",
        aliases=("pedot", "pedot:pss", "conducting polymer"),
        cic=MeasuredRange(
            low=2.3,
            high=3.6,
            units="mC/cm2",
            reference="cui_zhou2007",
            pulse_width_us=400.0,
            waveform="cathodal pulses",
            bias="benefits from positive bias",
            measured_area_cm2=2e-5,
            area_basis="geometric",
            note=(
                "Three peer-reviewed measurements cluster tightly: 2.3 mC/cm^2 for "
                "PEDOT on thin-film Pt (Cui & Zhou 2007), 2.5 +/- 0.1 mC/cm^2 for "
                "PEDOT/CNT (Luo et al. 2011), and 3.6 mC/cm^2 for PEDOT-PSS on ITO at "
                "1 ms (Nyberg et al. 2007). Cogan 2008 Table 2 instead reports "
                "15 mC/cm^2, four to six times higher than any of these, sourced to a "
                "meeting abstract that has not been replicated in the peer-reviewed "
                "literature. This package uses the peer-reviewed range."
            ),
        ),
        water_window=WaterWindow(
            cathodic_V=-0.9,
            anodic_V=0.6,
            reference="cogan2008",
        ),
        note=(
            "Cogan's headline 15 mC/cm^2 is an unreplicated conference-abstract value "
            "and is not used here; the peer-reviewed consensus is 2.3-3.6 mC/cm^2, "
            "comparable to iridium oxide rather than far above it. Conducting-polymer "
            "coatings also have well-documented delamination and long-term stability "
            "problems that no charge-injection limit captures."
        ),
    ),
    Material(
        key="Ta2O5",
        name="Tantalum / tantalum pentoxide capacitor electrode",
        mechanism="capacitive",
        aliases=("tantalum", "ta2o5", "tantalum pentoxide"),
        cic=MeasuredRange(
            low=0.088,
            high=0.15,
            units="mC/cm2",
            reference="rose1985_capacitor",
            pulse_width_us=100.0,
            waveform="cathodal pulses from a standing anodic bias",
            bias="+4.2 V DC in the only in vivo test (Schmidt et al. 1982)",
            medium="dilute phosphate-buffered saline, 300 ohm.cm, pH 7.3",
            measured_area_cm2=1.2e-3,
            area_basis="geometric",
            note=(
                "Read from Rose et al. (1985) rather than from Cogan's Table 2 summary, "
                "and the two disagree. Cogan reports '~0.5' mC/cm^2 with no conditions; "
                "the highest value anywhere in Rose et al. for a Ta2O5 electrode is "
                "0.26 mC/cm^2 (their Table III), and that is a slow-charge figure, not "
                "a pulsed one. The range stored here spans their two directly measured "
                "microelectrode designs, both at 0.1 ms: 88-140 uC/cm^2 for etched Ta "
                "at 80 % of a 10 V forming voltage, and 150 uC/cm^2 for the sintered "
                "electrode Schmidt et al. implanted. Their Table III best-reported "
                "260 uC/cm^2 is deliberately *not* the high end here -- it agrees with "
                "the DC capacitance (0.33 uF/mm^2 x 8 V), so it is a slow-charge figure, "
                "and pore resistance costs a pulsed electrode up to 80 % of that. Using "
                "it as the ceiling of a 100 us limit would overstate the pulsed capacity. "
                "Merrill 2005 Table 2's 700 uC/cm^2 "
                "traces to Guyton & Hambrecht's sintered porous *surface* disc, a "
                "macroelectrode, and does not apply intracortically. See "
                "neurostim.data.ta2o5_capacitor for all eight designs."
            ),
        ),
        water_window=None,
        note=(
            "Strictly capacitive, and therefore has no charge-injection limit in the "
            "sense the other materials do: Q/A = C x 0.8 V_f, so the limit is set by "
            "the roughness factor and the anodisation voltage chosen when the electrode "
            "was built, and ranges over 80-fold across published designs. The ceiling is "
            "dielectric breakdown at about 80 % of the forming voltage, not water "
            "electrolysis, which is why no window is recorded here -- use "
            "neurostim.data.ta2o5_capacitor.safe_operating_voltage_V with your own "
            "forming voltage. Two operating constraints have no analogue in a faradaic "
            "electrode: the film must be pulsed cathodically from a standing anodic "
            "bias, and it draws a continuous DC leakage current that must stay in the "
            "1-10 nA band. Pore resistance costs up to 80 % of the DC capacitance at "
            "stimulation pulse widths."
        ),
    ),
    Material(
        key="SS316LVM",
        name="316LVM stainless steel",
        mechanism="faradaic/capacitive",
        aliases=("ss", "stainless", "stainless steel", "316lvm", "316l"),
        cic=MeasuredRange(
            low=0.02,
            high=0.04,
            units="mC/cm2",
            reference="riedy_walter1996",
            pulse_width_us=100.0,
            waveform="capacitor-coupled monophasic, 60 pps, either polarity",
            medium=(
                "29 mM bicarbonate / 3 mM phosphate / 137 mM NaCl, 5% CO2 / 6% O2, "
                "pH 7.4, mimicking interstitial fluid"
            ),
            measured_area_cm2=1.6e-2,
            area_basis="geometric",
            recommended_policy="conservative",
            recommendation_note=(
                "Riedy & Walter's paper exists to argue the 40 uC/cm^2 figure down. "
                "They give two reasons: it rests on a one-hour pulsing study, and only "
                "half of it is available for non-faradaic double-layer transfer. Their "
                "own year-long experiment at 20 uC/cm^2 concludes that 20 is the maximum "
                "feasible density for functional stimulation. Applying 40 does not pick "
                "the permissive end of a measured range; it applies the number the cited "
                "work was written to dispute"
            ),
            note=(
                "Read from Riedy & Walter's primary text. 40 uC/cm^2 is the "
                "long-standing recommendation, but they argue it down: it rests on a "
                "one-hour pulsing study, and only 20 uC/cm^2 of it is available for "
                "non-faradaic double-layer transfer. Their own year-long experiment at "
                "20 uC/cm^2 concludes that this is the maximum feasible density for "
                "functional stimulation, so the conservative end here is the authors' "
                "recommendation rather than merely the low end of a range. Corroborated "
                "by Merrill 2005 Table 2 (40-50 uC/cm^2 geometric). Stainless steel "
                "does not appear in Cogan 2008 Table 2."
            ),
        ),
        water_window=WaterWindow(
            cathodic_V=-1.2,
            anodic_V=1.2,
            reference="riedy_walter1996",
            scale="of polarisation from rest (measured vs SCE)",
            note=(
                "Not a water window: this is the reported reversible charge-injection "
                "limit for 316LVM, 1.2 V of polarisation in either direction, restated "
                "as a symmetric window so the polarisation check can run. It is a "
                "magnitude relative to the resting potential, not an absolute potential "
                "versus a reference, so it is only meaningful when resting_potential_V "
                "is your electrode's measured open-circuit value. It is also not a "
                "cliff: Riedy & Walter exceeded it for a year in both polarities and "
                "saw tarnishing that stopped progressing after 15 days. Consistency "
                "check -- 20 uC/cm^2 over 1.2 V implies 17 uF/cm^2, within a whisker of "
                "the 20 uF/cm^2 smooth-metal double-layer value, which is exactly what "
                "'available for double-layer injection' should mean."
            ),
        ),
        chronic_threshold=ChronicThreshold(
            low_uC_cm2=20.0,
            high_uC_cm2=20.0,
            mechanism="pitting corrosion, cathodic-first only",
            reference="riedy_walter1996",
            note=(
                "After 365 days at 20 uC/cm^2, SEM found pitting around the tip of the "
                "cathodic-first electrode and no corrosion at all on the anodic-first "
                "one; both tarnished. This reverses the prior claim that anodic-first "
                "is unsuitable for stainless steel, and it is the opposite of platinum, "
                "where anodic-first dissolves faster. Albumin at 0.4 and 4.0 g/L had no "
                "effect on either the corrosion or the transients"
            ),
        ),
        note=(
            "Not a CNS chronic-stimulation material in the Cogan review; the cited "
            "work is peripheral/functional stimulation. Corrosion, not tissue damage, "
            "is usually the binding constraint. Unusually for this database the chronic "
            "threshold and the conservative charge-injection limit coincide at "
            "20 uC/cm^2, because the same experiment established both."
        ),
    ),
)

MATERIALS: dict[str, Material] = {m.key: m for m in _MATERIAL_LIST}

_ALIAS_INDEX: dict[str, str] = {}
for _m in _MATERIAL_LIST:
    _ALIAS_INDEX[_m.key.lower()] = _m.key
    for _alias in _m.aliases:
        _ALIAS_INDEX[_alias.lower()] = _m.key


def get_material(name: str) -> Material:
    """Look up a material by key or alias, case-insensitively.

    ``"SS"`` resolves to 316LVM stainless steel for backward compatibility with the
    0.1.0 prototype, but note that its limit changed from 0.05 to 0.02-0.04 mC/cm^2
    once it was traced to a primary source.
    """
    try:
        return MATERIALS[_ALIAS_INDEX[name.strip().lower()]]
    except KeyError:
        raise KeyError(
            f"Unknown material {name!r}. Known materials: {sorted(MATERIALS)}"
        ) from None


def list_materials() -> list[Material]:
    """All materials in registry order."""
    return list(_MATERIAL_LIST)


def inherited_label(material_name: str, reference: str) -> str:
    """How an inherited constant is attributed on every surface (ledger 25)."""
    return f"published for {material_name} ({reference}), not measured on this electrode"


class _Inherit:
    """Sentinel: keep the base material's constant, labelled as inherited."""

    def __repr__(self) -> str:
        return "INHERIT"


INHERIT = _Inherit()
"""The default for :func:`with_measured_cic`'s ``water_window`` and ``chronic_threshold``."""


def with_measured_cic(
    material: Material,
    low_uC_cm2: float,
    high_uC_cm2: float | None = None,
    *,
    pulse_width_us: float | None = None,
    note: str = "",
    water_window: WaterWindow | tuple[float, float] | _Inherit | None = INHERIT,
    chronic_threshold: ChronicThreshold | tuple[float, float] | _Inherit | None = INHERIT,
) -> Material:
    """Return a copy of ``material`` with a locally measured charge-injection limit.

    Use this when you have characterised your own electrodes. The result carries the
    ``user_measurement`` provenance key rather than the material's original citation:
    displaying a published reference next to a number that did not come from that paper
    would misattribute your measurement, which is the exact failure this package exists
    to prevent.

    **The other constants** (ledger 25). The water window and the chronic threshold were
    carried over untouched and presented as the user material's own. Dropping them would
    remove limits -- the platinum dissolution threshold among them -- which is the less
    conservative direction. So by default (``INHERIT``) each is kept, with its published
    value and reference, marked ``inherited_from`` the base material, and every render
    says "published for <base> (<reference>), not measured on this electrode". Pass:

    - a ``(cathodic_V, anodic_V)`` or ``(low_uC_cm2, high_uC_cm2)`` pair to use your own
      value, cited as ``user_measurement`` and unverified; or a ``WaterWindow`` /
      ``ChronicThreshold`` you built;
    - ``None`` to drop it. The check that needed it does not run, says why, and the
      assessment's incomplete-limits note names the drop.
    """
    if not math.isfinite(low_uC_cm2) or low_uC_cm2 <= 0:
        raise ValueError(f"low_uC_cm2 must be finite and > 0, got {low_uC_cm2!r}")
    high = low_uC_cm2 if high_uC_cm2 is None else high_uC_cm2
    if not math.isfinite(high) or high <= 0:
        raise ValueError(f"high_uC_cm2 must be finite and > 0, got {high_uC_cm2!r}")
    measured = MeasuredRange(
        low=low_uC_cm2 * 1e-3,
        high=high * 1e-3,
        units="mC/cm2",
        reference="user_measurement",
        verified=False,
        pulse_width_us=pulse_width_us,
        area_basis="geometric",
        note=note or "User-supplied measurement, not from published literature.",
    )
    dropped: list[str] = []
    window = material.water_window
    if isinstance(water_window, _Inherit):
        if window is not None:
            window = replace(window, inherited_from=material.name)
    elif water_window is None:
        window = None
        dropped.append("water window")
    elif isinstance(water_window, tuple):
        window = WaterWindow(
            water_window[0], water_window[1], reference="user_measurement", verified=False,
            note="User-supplied potential limits, not from published literature.",
        )
    else:
        window = water_window
    threshold = material.chronic_threshold
    if isinstance(chronic_threshold, _Inherit):
        if threshold is not None:
            threshold = replace(threshold, inherited_from=material.name)
    elif chronic_threshold is None:
        threshold = None
        dropped.append("chronic threshold")
    elif isinstance(chronic_threshold, tuple):
        threshold = ChronicThreshold(
            chronic_threshold[0], chronic_threshold[1],
            mechanism=(
                material.chronic_threshold.mechanism
                if material.chronic_threshold is not None
                else "user-supplied degradation"
            ),
            reference="user_measurement", verified=False,
            note="User-supplied threshold, not from published literature.",
        )
    else:
        threshold = chronic_threshold
    kept = []
    if window is not None and window.inherited_from:
        kept.append("water window")
    if threshold is not None and threshold.inherited_from:
        kept.append("chronic threshold")
    reworded = f"User-measured charge-injection limit on {material.name}."
    if kept:
        reworded += (
            f" Its {' and '.join(kept)} {'are' if len(kept) > 1 else 'is'} "
            f"{material.name}'s published value{'s' if len(kept) > 1 else ''}, marked "
            f"inherited, not measured on this electrode."
        )
    if material.note:
        reworded += f" {material.name}'s published note: {material.note}"
    return replace(
        material,
        cic=measured,
        water_window=window,
        chronic_threshold=threshold,
        note=reworded,
        dropped=tuple(dropped),
    )
