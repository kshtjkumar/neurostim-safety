"""Cogan, Ludwig, Welle & Takmakov (2016), the modern re-evaluation of damage limits.

J. Neural Eng. 13(2):021001. Two of the four authors are at FDA/CDRH, which makes this
the closest thing in the open literature to a regulator's view of where the Shannon
criterion holds and where it does not.

Three conclusions here change how this package should be used
--------------------------------------------------------------
1. **Microelectrodes do not obey the Shannon relation.** Damaging levels for
   microelectrodes fall well below a k = 1.85 line while their charge densities sit well
   above 30 uC/cm^2. What governs them instead is charge *per phase*, with a threshold
   around :data:`MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE`.
2. **In vivo charge-injection capacity is far below the saline value.** Every limit in
   :mod:`neurostim.materials` is measured in saline. See :data:`IN_VIVO_DERATING`.
3. **Charge density alone predicts nothing.** Their words: "It is possible to stimulate
   below 30 uC/cm^2 and generate tissue damage; conversely, it is possible to stimulate
   up above that level and not produce tissue damage."

A discrepancy noticed while transcribing
----------------------------------------
The paper states that McCreery's damaging 12 uC/cm^2, 6 uC/phase condition has "a k
value for this stimulus intensity of only 1.4". By the Shannon relation that point is
``log10(6) + log10(12) = 1.86``. Their other worked example in the same passage --
60 uC/cm^2 on a 0.005 cm^2 electrode giving "k ~ 1.25" -- evaluates to 1.255 and agrees
exactly, so the relation is the standard one and the 1.4 appears to be a slip. This
package uses 1.86 for that point, which is what
:mod:`neurostim.data.mccreery1990` computes from the tabulated values.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- the microelectrode regime ----------------------------------------------------

MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE = 4.0
"""Charge-per-phase damage threshold emerging from the microelectrode data.

Attributed to McCreery et al. (1994, 2010) and drawn as a vertical line in their
figure 5. The authors caution against over-reading it exactly as they caution against
over-reading the Shannon line: it will also depend on pulse frequency, duty cycle and
the type of neural tissue.
"""

MICROELECTRODE_PHYSIOLOGICAL_THRESHOLD_NC_PER_PHASE = (1.0, 2.0)
"""Physiological (activation) thresholds reported for ~1000 um^2 electrodes.

On that area this corresponds to 100-200 uC/cm^2, several times the 30 uC/cm^2 approved
for DBS -- which is the crux of the paper: useful microstimulation requires charge
densities that the macroelectrode limit forbids.

McCreery 2008 (``mccreery2008``), cited via this review (author manuscript p. 11); the
primary is not in the library (ledger 78, S-25)."""

MACRO_MICRO_BOUNDARY_DIAMETER_UM = (200.0, 300.0)
"""Diameter range where current thresholds stop scaling as macroelectrodes.

From Butterwick et al. (2007); equivalently 3e-4 to 7e-4 cm^2.
"""

MACRO_MICRO_BOUNDARY_AREA_CM2 = (3e-4, 7e-4)
"""The same boundary expressed as geometric surface area."""

FAR_FIELD_DISTANCE_ELECTRODE_DIAMETERS = (2.0, 5.0)
"""Far-field begins at roughly 2-5 times the largest exposed electrode dimension."""

MICROELECTRODE_POINT_SOURCE_DISTANCE_UM = 50.0
"""Beyond about 50 um a typical microelectrode (200-2000 um^2) behaves as a point source."""


def is_microelectrode(area_cm2: float) -> bool:
    """Whether an electrode is small enough that the Shannon relation stops applying.

    Uses the lower edge of the reported boundary, so the classification is conservative:
    an electrode is only treated as a microelectrode once it is unambiguously below the
    range where macroelectrode scaling was observed.
    """
    return area_cm2 < MACRO_MICRO_BOUNDARY_AREA_CM2[0]


def in_regime_transition(area_cm2: float) -> bool:
    """Whether an electrode falls inside the ambiguous macro/micro boundary band."""
    low, high = MACRO_MICRO_BOUNDARY_AREA_CM2
    return low <= area_cm2 <= high


# --- in vivo versus saline --------------------------------------------------------


@dataclass(frozen=True)
class Derating:
    """How far an in vivo charge-injection capacity falls below the saline value."""

    factor_low: float
    factor_high: float
    evidence: str

    @property
    def worst(self) -> float:
        """The largest reported reduction."""
        return self.factor_high

    def describe(self) -> str:
        """Human-readable derating range."""
        body = (
            f"{self.factor_low:g}-{self.factor_high:g}x"
            if self.factor_high > self.factor_low
            else f"{self.factor_high:g}x"
        )
        return f"{body} lower in vivo than in saline ({self.evidence})"


LEUNG_MATCHED_PULSE_WIDTH_QUOTE = (
    "suprachoroidal Qinj in vivo was between 8.7 times less (200μs pulsewidth) and "
    "3.2 times less (3200-μs pulsewidth) than that measured in vitro. These factors "
    "were determined by dividing the in vitro Qinj by the mean in vivo Qinj at the "
    "respective pulsewidths."
)
"""Leung et al. (IEEE TBME 62(3):849-857), p. 852, as printed (the micro sign is the
PDF's Greek mu). The derating factors are theirs, each in vitro value over the mean in
vivo value at the same pulse width (ledger 71)."""


HU_IN_VIVO_QUOTE = (
    "For the chosen compliance limit, the in vivo value is about 10% of the in vitro "
    "ones for both electrodes."
)
"""Hu et al. (Proc. IEEE EMBS 2006:886-889), p. 888: the AIROF derating's source (S-7)."""


IN_VIVO_DERATING: dict[str, Derating] = {
    # Leung et al.'s own pulse-width-matched factors (ledger 71, C4.5). The range was 2-14x,
    # the best in-vitro value divided by the worst in-vivo one across different pulse
    # widths: the low end more permissive than the source's 3.2, and the high end above
    # even Cogan 2016's "as much as a factor of 10".
    "Pt": Derating(
        3.2,
        8.7,
        "Leung et al. 2014, p. 852: suprachoroidal Qinj in vivo 8.7 times less at 200 us "
        "and 3.2 times less at 3200 us than in vitro, at matched pulse widths (in vitro "
        "34-54 uC/cm^2; in vivo 3.84-16.6 acute, 6.99-15.8 chronic)",
    ),
    "PtIr": Derating(3.2, 8.7, "assumed to follow platinum; not measured separately"),
    # Hu et al.'s own in vivo sentence (ledger 77, S-7). The evidence used to say their
    # "3-4 mC/cm^2 is about ten times what the same films deliver in vivo", welding the
    # in vivo result to a different sentence of theirs, which compares AIROF with platinum.
    "AIROF": Derating(
        10.0,
        10.0,
        "Hu et al. 2006, p. 888: 'the in vivo value is about 10% of the in vitro ones for "
        "both electrodes' (their in vitro 1.69 and 1.18 mC/cm^2 in PBS; in the bird brain "
        "0.14 and 0.15)",
    ),
    # Both sources named (ledger 77, S-8, user decision (b)): the 2-3 is Kane's, the 4
    # the review's. The evidence named only Kane while the range went to 4.
    "SIROF": Derating(
        2.0,
        4.0,
        "Kane et al. 2013 (author manuscript p. 7): chronically implanted in cat cortex, "
        "'the maximum charge capacity in vivo was reduced by a factor of 2-3'; the upper "
        "4 is Cogan et al. 2016's review figure (author manuscript p. 8), 'a factor of "
        "four lower with SIROF microelectrodes'",
    ),
}
"""Reported reductions in charge-injection capacity measured in vivo versus in saline.

The paper reports "as much as a factor of 10 lower for platinum and activated iridium
oxide (AIROF), and a factor of four lower with SIROF microelectrodes", and separately
that porous platinum lost a factor of eight after about 45 days in rabbit sclera
(Terasawa et al. 2013).

These are **not** applied automatically. Applying a blanket 10x would make the package
unusable for acute work where the saline value is the right one, and the derating is
material-, geometry- and duration-specific. It is surfaced as a caution so the choice
is yours and visible.
"""

POROUS_PLATINUM_DERATING = Derating(
    8.0, 8.0, "8x after ~45 days in rabbit sclera, Terasawa et al. 2013"
)
"""Porous platinum specifically; worse than smooth platinum because pores foul."""


def derating_for(material_key: str) -> Derating | None:
    """In vivo derating for a material, or ``None`` when none is reported."""
    return IN_VIVO_DERATING.get(material_key)


# --- clinical reference points ----------------------------------------------------

DBS_APPROVED_CHARGE_DENSITY_UC_CM2 = 30.0
"""The limit the first US DBS approval (Medtronic Activa, 1997) was granted under.

Its origin: extending the charge-density / charge-per-phase line for a 0.06 cm^2
macroelectrode out to the Shannon line at k ~ 1.75 (Kuncel & Grill 2004). It is a
device-specific approval condition, not a law of tissue.
"""

DBS_TYPICAL_CLINICAL_CHARGE_DENSITY_UC_CM2 = 8.0
"""Charge density actually used clinically in DBS, well under the approved limit.

Estimated by the authors from Burbaud et al. (2002) and Haberler et al. (2000) assuming
1100 ohm electrode resistance, together with a maximum 0.5 uC per phase. The scarcity of
damage in post-mortem DBS studies is attributed to this, not to the 30 uC/cm^2 ceiling.
"""

SMOOTH_PT_SALINE_CIC_UC_CM2 = (35.0, 100.0)
"""Charge-injection capacity of smooth platinum in physiological saline."""

POROUS_PT_SALINE_CIC_UC_CM2 = 1000.0
"""Porous platinum can reach about 1 mC/cm^2 in saline."""

PT_EDGE_CORROSION_CHARGE_DENSITY_UC_CM2 = 240.0
"""Preferential corrosion at platinum disc edges was reported at this density.

Wang & Weiland 2012 (``wang_weiland2012``), cited via this review (author manuscript
p. 11); the primary is not in the library (ledger 78, S-25)."""

AIROF_BIAS_SAFE_CHARGE_NC_PER_PHASE = 3.6
"""Biased AIROF showed no deleterious tissue effect at or below this charge per phase."""

COGAN_FIGURE_1_K = 1.85
"""The k the authors draw as a qualitative boundary over their expanded dataset.

They add: "A more conservative estimate of damage thresholds would use a lower k."
"""

CLINICAL_DEVICES_RESPECT_K_RANGE = (1.5, 1.8)
"""Most clinical neural stimulation devices sit below the Shannon line in this k band."""

REFERENCE = "cogan2016"
