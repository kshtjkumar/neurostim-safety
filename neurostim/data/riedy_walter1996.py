"""316LVM stainless steel under a year of continuous pulsing.

Why this paper decides the stainless-steel row
----------------------------------------------
Neither stainless-steel figure is Riedy and Walter's own measurement, and the record
says so (ledgers 72, 73). The 40 uC/cm^2 "has been reported" (abstract, p. 660; their
ref. [5] and others), and they argue it down as resting on one-hour pulsing studies
(p. 662). Their 20 uC/cm^2 maximum is adopted, in their words, "Based on this report":
a tissue-damage figure from a cited source, their ref. [8], "not damaged as long as the
charge density for biphasic pulses is kept below 0.2 uC/mm^2 (20 uC/cm^2)" (p. 663).

What they measured is corrosion: 365 days of capacitor-coupled pulsing at 20 uC/cm^2,
after which "biphasic pulsing for stainless steel electrodes is possible provided that
the charge injection is kept below 20 uC/cm^2" (p. 662). So the conservative end the
package applies is the figure they endorse, from a cited tissue-damage source, and
consistent with their own year-long corrosion result -- not a charge-injection capacity
anyone in this paper measured.

The quotations are stored below as the PDF's text layer prints them: its OCR renders
the micro sign as "p", so "pC/cm2" is uC/cm^2.

The two cited sources, by position in their reference list (p. 663, read from the page
image and counted in list order, matching the citation order in the text):

- ref. [5], for the 40 uC/cm^2 and the 1.2 V limit: Lan, Daroux & Mortimer, "Pitting corrosion of high strength alloy stimulation electrodes under dynamic conditions", J Electrochem Soc 136:947-954 (printed as 1981);
- ref. [8], for the 20 uC/cm^2 and the "reversible charge injection limit" term:
  Robblee & Rose, "Electrochemical guidelines for selection of protocols and electrode materials for neural stimulation", in Agnew & McCreery (eds), Neural Prostheses: Fundamental Studies, Prentice-Hall 1990, pp. 25-66.

Neither is in the package's library, so both are attributions via Riedy & Walter, not
verified primaries (ledger 152). J Electrochem Soc volume 136 suggests 1989 rather than
the printed 1981; that is not checked here.

Two findings that reverse received wisdom
-----------------------------------------
**Anodic-first is not the dangerous polarity here.** The prior literature held that
anodic-first waveforms are unsuitable for stainless steel. After a year at 20 uC/cm^2,
SEM found pitting corrosion around the tip of the *cathodically* pulsed electrode and no
evidence of corrosion at all on the anodically pulsed one. Both tarnished. This is the
opposite of the platinum case, where anodic-first dissolves faster, and it is why
:data:`ANODIC_FIRST_SAFE_AT_LOW_DENSITY` exists rather than a blanket polarity rule.

**Protein does not matter.** Plasma proteins are reported to promote corrosion by
inhibiting repassivation, so they added albumin at interstitial (0.4 g/L) and ten times
interstitial (4.0 g/L) concentrations. No effect on corrosion response or on the
electrical transients. A protein-free bath is adequate for in vitro corrosion work on
this alloy -- which is worth knowing, because it is the cheaper experiment.

What "exceeding the limit" turned out to mean
---------------------------------------------
The reversible charge injection limit for 316LVM is reported as 1.2 V -- by citation, of
their ref. [5] (p. 662; ledger 151). Their measured
polarisation exceeded it for both polarities, for a year, and produced only tarnishing
that stopped progressing after 15 days. They suggest the tarnish layer passivates the
surface. So the 1.2 V figure is not a cliff edge; it marks where irreversible faradaic
processes begin, not where the electrode fails.

The transient decomposition
---------------------------
Riedy and Walter separate a measured pulse exactly as :mod:`neurostim.transient` does:

- ``E_acc``, the access voltage, the ohmic drop through the electrolyte;
- ``E_max``, the maximum potential excursion **after subtracting** ``E_acc``;
- ``E_ipp``, the interpulse potential, measured just before the next pulse.

They report ``E_ipp`` is *not* causal in corrosion, contrary to the standing assumption:
it varied widely but stayed below 0.7 V while both polarities corroded differently.
"""

from __future__ import annotations

from dataclasses import dataclass

REFERENCE = "riedy_walter1996"

# --- quoted from the paper (IEEE TBME 43(6):660-663), as its text layer prints them ----

REPORTED_40_QUOTE = (
    "The safe charge injection density for pulsing of 316LVM electrodes has been "
    "reported to be 40 pC/cm2. However, only 20 pC/cm2 is available for nonfaradic "
    "charge transfer and double layer charge injection."
)
"""Abstract, p. 660: the 40 is reported, not measured here."""

OWN_RESULT_QUOTE = (
    "This result suggests that biphasic pulsing for stainless steel electrodes is "
    "possible provided that the charge injection is kept below 20 pC/cm2 and is in "
    "contrast to reports indicating that 40 pC/cm2 is suitable for charge injection "
    "with 316LVM electrodes [ 5 ] ."
)
"""p. 662: what their year-long corrosion test supports."""

REVERSIBLE_LIMIT_QUOTE = (
    "is referred to as the reversible charge injection limit [8] and is reported to "
    "be 1.2 V for 316LVM [ 5 ] ."
)
"""p. 662: the 1.2 V limit, cited from their ref. [5] (ledger 151)."""

TISSUE_20_QUOTE = (
    "It has recently been suggested that tissue surrounding the stimulating electrode "
    "is not damaged as long as the charge density for biphasic pulses is kept below "
    "0.2 pC/mm2 (20 pC/cm2) [8]. Based on this report, 20 pC/cm2 appears to be the "
    "maximum charge injection density feasible for FNS application."
)
"""p. 663: the 20 uC/cm^2 maximum, adopted from a cited tissue-damage report, ref. [8]."""

# --- protocol ---------------------------------------------------------------------

PULSE_WIDTH_US = 100.0
PULSE_RATE_PPS = 60.0
WAVEFORM = "capacitor-coupled monophasic, anodic-first or cathodic-first"
DISCHARGE_CAPACITOR_UF = 0.47
DISCHARGE_TIME_CONSTANT_MS = 0.96
"""RC of the discharge path: 0.47 uF into access + 1.8 kohm shunt + 100 ohm sense."""

CHRONIC_CHARGE_DENSITY_UC_CM2 = 20.0
CHRONIC_CURRENT_MA = 3.8
CHRONIC_DURATION_DAYS = 365

PROTEIN_STUDY_CHARGE_DENSITY_UC_CM2 = 40.0
PROTEIN_STUDY_CURRENT_MA = 11.2
PROTEIN_STUDY_DURATION_DAYS = 10

WIRE_DIAMETER_MM = 0.17
"""7 mil single-strand 316LVM, annealed, 670 MPa tensile."""
EXPOSED_LENGTH_CHRONIC_MM = 3.0
EXPOSED_LENGTH_PROTEIN_MM = 5.0

ALLOY_COMPOSITION_PERCENT = {"Cr": 17.0, "Ni": 12.0, "Mo": 2.5, "Fe": "balance"}

ELECTROLYTE = (
    "29 mM bicarbonate, 3 mM phosphate, 137 mM NaCl, purged with 5% CO2 / 6% O2 "
    "to pH 7.4, replaced weekly"
)
"""Mimics interstitial fluid rather than plain PBS. Reference electrode was SCE."""

# --- limits -----------------------------------------------------------------------

RECOMMENDED_LIMIT_UC_CM2 = 40.0
"""The long-standing recommendation, which this paper argues down."""

NONFARADAIC_LIMIT_UC_CM2 = 20.0
"""Charge available for double-layer injection alone, and the paper's own ceiling."""

REVERSIBLE_INJECTION_LIMIT_V = 1.2
"""Reported reversible charge injection limit for 316LVM, in volts of polarisation.

A magnitude in either direction, not an absolute potential versus a reference. Compare
against ``E_max``, the excursion left after the access voltage is subtracted.
"""

ANODIC_FIRST_SAFE_AT_LOW_DENSITY = True
"""Whether anodic-first pulsing is acceptable at 20 uC/cm^2. Measured, not assumed."""

TARNISH_ONSET_DAYS = 15
"""Tarnishing appeared by day 15 for both polarities, then stopped progressing."""

PROTEIN_AFFECTS_CORROSION = False

# --- one-year drift ---------------------------------------------------------------


@dataclass(frozen=True)
class TransientDrift:
    """How far one transient parameter moved over 365 days of pulsing."""

    parameter: str
    polarity: str
    increase_V: float
    note: str = ""


ONE_YEAR_DRIFT: tuple[TransientDrift, ...] = (
    TransientDrift("E_acc", "anodic-first", 0.47, "electrolyte-path resistance rose"),
    TransientDrift("E_acc", "cathodic-first", 0.55),
    TransientDrift("E_max", "anodic-first", 0.73, "roughly a doubling"),
    TransientDrift("E_max", "cathodic-first", 0.63),
)

INTERIM_EXTREME_V_VS_SCE = 2.0
"""Electrode potential reached transiently early in the anodic-first run."""

SUSTAINED_POTENTIAL_V_VS_SCE = 1.8
"""Average over the subsequent 3000 h, which the authors flag as more significant
than the final value if corrosion is an ongoing process."""

MAX_INTERPULSE_POTENTIAL_V = 0.7
"""``E_ipp`` stayed below this throughout, for both polarities."""

# --- Table I: 10-day protein study at 40 uC/cm^2 ----------------------------------


@dataclass(frozen=True)
class TransientMeasurement:
    """One row of Table I: mean +/- SD over n = 4 electrodes."""

    bath: str
    parameter: str
    initial_V: float
    initial_sd_V: float
    final_V: float
    final_sd_V: float
    n: int = 4

    @property
    def change_V(self) -> float:
        """Drift over the 10-day run."""
        return self.final_V - self.initial_V


TABLE_I: tuple[TransientMeasurement, ...] = (
    TransientMeasurement("no protein", "E_max", 1.10, 0.08, 2.01, 0.24),
    TransientMeasurement("no protein", "E_acc", 1.37, 0.24, 2.09, 0.36),
    TransientMeasurement("no protein", "E_ipp", -0.25, 0.07, -0.01, 0.44),
    TransientMeasurement("interstitial protein", "E_max", 1.34, 0.18, 2.21, 0.25),
    TransientMeasurement("interstitial protein", "E_acc", 1.31, 0.10, 1.69, 0.22),
    TransientMeasurement("interstitial protein", "E_ipp", -0.06, 0.04, -0.11, 0.09),
    TransientMeasurement("ten times interstitial", "E_max", 1.24, 0.12, 1.70, 0.32),
    TransientMeasurement("ten times interstitial", "E_acc", 1.29, 0.10, 1.55, 0.29),
    TransientMeasurement("ten times interstitial", "E_ipp", -0.10, 0.08, -0.08, 0.03),
)
"""Protein baths: 0 g/L, 0.4 g/L (interstitial) and 4.0 g/L albumin.

Every ``E_max`` final value exceeds the 1.2 V reversible limit, in every bath.
"""


def wire_area_cm2(exposed_length_mm: float, diameter_mm: float = WIRE_DIAMETER_MM) -> float:
    """Lateral area of the exposed wire, in cm^2.

    The paper does not state whether the tip face is included. Taking the lateral
    surface alone reproduces their stated currents to about 5 % on the protein study
    (11.2 mA) and about 15 % on the one-year study (3.8 mA), which brackets the
    ambiguity rather than hiding it.
    """
    import math

    if exposed_length_mm <= 0 or diameter_mm <= 0:
        raise ValueError("exposed length and diameter must both be > 0")
    return math.pi * (diameter_mm * 0.1) * (exposed_length_mm * 0.1)


def current_for_charge_density_mA(
    charge_density_uC_cm2: float,
    exposed_length_mm: float,
    *,
    pulse_width_us: float = PULSE_WIDTH_US,
) -> float:
    """Constant current that delivers ``charge_density_uC_cm2`` in one pulse."""
    area = wire_area_cm2(exposed_length_mm)
    charge_uC = charge_density_uC_cm2 * area
    return charge_uC / pulse_width_us * 1e3


def exceeds_reversible_limit(polarisation_V: float) -> bool:
    """Whether a measured ``E_max`` is past the 1.2 V reversible injection limit.

    True for every final value in :data:`TABLE_I`, which is the point: exceeding it
    produced tarnishing that self-limited, not failure.
    """
    return abs(polarisation_V) > REVERSIBLE_INJECTION_LIMIT_V
