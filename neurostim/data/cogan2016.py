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
    shortest_measured_pulse_width_us: float | None = None
    """Below this pulse width the factor rests on no measurement, and a limit derated by it
    is provisional (ledger 156). ``None`` where the source gives no pulse-width range."""

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


LEUNG_IN_VITRO_QUOTE = (
    "Qinj increased with pulsewidth from 35 to 54 \u03bcC/cm2 for respective pulse widths "
    "of 100 to 3200 \u03bcs per phase in vitro"
)
"""Leung et al., abstract, p. 849. Their results (p. 852) say "34 to 54"; the abstract's 35
is the larger, so the factor built on it is the larger (ledger 156)."""

LEUNG_ACUTE_IN_VIVO_QUOTE = (
    "The mean suprachoroidal Qinj in the acutely implanted animals was between 3.84 to 16.6 "
    "\u03bcC/cm2 for pulsewidths of 100 to 3200 \u03bcs (n = 18)"
)
"""Leung et al., p. 852."""

LEUNG_IN_VITRO_100US_UC_CM2 = 35.0
LEUNG_ACUTE_IN_VIVO_100US_UC_CM2 = 3.84
LEUNG_SHORTEST_MEASURED_PULSE_WIDTH_US = 100.0
LEUNG_CORTEX_400US_UC_CM2 = 4.63
"""Subdural (cortical) Qinj at 400 us, "4.63 \u00b1 0.04 \u03bcC/cm2 (n = 4)", p. 852."""

LEUNG_FIG4_DIGITISED_UC_CM2: dict[str, dict[int, float]] = {
    "in_vitro": {100: 33.51, 200: 34.23, 400: 36.29, 800: 39.97, 1600: 46.26, 3200: 53.92},
    "acute": {100: 3.883, 200: 6.032, 400: 7.692, 1600: 12.357, 3200: 16.605},
    "chronic": {200: 7.03, 400: 8.77, 1600: 12.19, 3200: 15.87},
    "intracochlear": {400: 10.818},
}
"""Leung et al. Fig. 4 (p. 853), read from the embedded raster; see
:data:`PT_IN_VIVO_DERATING_DOC` for the method and calibration. Suprachoroidal acute and
chronic, intracochlear chronic; the subdural point is :data:`LEUNG_CORTEX_400US_UC_CM2`."""

LEUNG_CORTEX_400US_FACTOR = LEUNG_FIG4_DIGITISED_UC_CM2["in_vitro"][400] / LEUNG_CORTEX_400US_UC_CM2
"""In vitro at 400 us (digitised, 36.29) over the cortical 4.63: about 7.84x."""

PT_IN_VIVO_DERATING = LEUNG_IN_VITRO_100US_UC_CM2 / LEUNG_ACUTE_IN_VIVO_100US_UC_CM2
PT_IN_VIVO_DERATING_DOC = """\
Pt and PtIr in vivo: 35/3.84 = 9.11x at every pulse width (ledger 156, user decision (D)).

The factor is the largest matched reduction in Leung et al.'s data: 35 uC/cm^2 in vitro
at 100 us (abstract, p. 849) over the 3.84 acute suprachoroidal mean at 100 us (p. 852).
Their text's "8.7 times less (200us pulsewidth)" (p. 852) is the 100 us pair: Fig. 4
(p. 853) gives 33.51/3.883 = 8.63 at 100 us, and about 5.7x at 200 us (34.23/6.032). It
was the factor used before, and it sat about 5 % under their own 100 us value. Their
cortical point, 4.63 uC/cm^2 at 400 us (p. 852), is 7.84x against the in vitro 36.29
there, below 9.11. Below 100 us they measured nothing, and they write that "the reduction
in the in vivo Qinj was greater at short pulsewidths" (p. 853), so a limit derated at a
shorter pulse is provisional.

A per-width curve was declined. Fig. 4's suprachoroidal factors fall to 5.7x at 200 us,
4.7x at 400, 3.8x at 1600 and 3.4x at 3200, so a curve built on them relaxes the in-vivo
limit 1.5-2.7x above 100 us on single-site data, and it misses cortex, where the one
measured point (7.84x at 400 us) sits well above the suprachoroidal 4.7x. The flat
factor relaxes nothing.

Digitisation method. Fig. 4 is an 800 x 945 greyscale raster embedded at 300 ppi,
extracted with pdfimages. Its horizontal gridlines were located as rows of near-uniform
grey across the plot width: in vitro 0-60 uC/cm^2 at 6.81 px per uC/cm^2, in vivo 0-20 at
20.48 px per uC/cm^2. Marker centres were taken as the centroids of the dark connected
regions after a morphological opening (circles; the acute bars with a 3 x 13 element),
and of the grey outlines for the chronic squares. The pulse-width axis was fixed by the
six in vitro centroids, 0.2005 px per us, which agree with 100-3200 us to under a pixel.
Calibration against values the text quotes: acute 100 us 3.883 (text 3.84), acute
3200 us 16.605 (16.6), intracochlear 400 us 10.818 (10.8), in vitro 3200 us 53.92 (54).
That is about one pixel: 0.05 uC/cm^2 in vivo, 0.15 in vitro. The digitised values are
recorded for the record; the factor itself uses only the two quoted numbers.
"""

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
    # The flat 9.11x (ledger 156, Phase 4 review M2, user decision (D)); see
    # PT_IN_VIVO_DERATING_DOC. 8.7x sat under Leung's own 100 us pair.
    "Pt": Derating(
        3.2,
        PT_IN_VIVO_DERATING,
        "Leung et al. 2015: the largest matched reduction in their data, 35 uC/cm^2 in "
        "vitro (abstract, p. 849) over 3.84 acute in vivo (p. 852) at 100 us, 9.11x, "
        "applied at every pulse width; their '8.7 times less (200us pulsewidth)' (p. 852) "
        "is the 100 us pair, Fig. 4 (p. 853) giving about 5.7x at 200 us; 3.2x at "
        "3200 us; cortex 7.84x at 400 us (4.63 uC/cm^2, p. 852); nothing measured below "
        "100 us, where they report the reduction grows",
        shortest_measured_pulse_width_us=LEUNG_SHORTEST_MEASURED_PULSE_WIDTH_US,
    ),
    "PtIr": Derating(
        3.2,
        PT_IN_VIVO_DERATING,
        "assumed to follow platinum; not measured separately",
        shortest_measured_pulse_width_us=LEUNG_SHORTEST_MEASURED_PULSE_WIDTH_US,
    ),
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
