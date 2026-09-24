"""Elwassif et al. (2006) Table I, used to validate this package's thermal model.

The paper solves the Pennes equation by finite elements around a real Medtronic DBS
lead. This package solves it analytically around an equal-area sphere. Table I varies
one parameter at a time, which makes it a direct test of whether the analytic scalings
are right.

Result of that comparison
-------------------------
========================  ==========================  =====================
Reported behaviour        Analytic prediction         Agreement
========================  ==========================  =====================
peak rise linear in sigma ``P = sigma * int|grad V|^2`` 0.7 % over 4 points
peak rise as 1/kappa      ``dT = P / (4 pi kappa a)``   0.9 % over 4 points
perfusion attenuation     ``1 / (1 + a/L)``             within 7-8 %
========================  ==========================  =====================

The residual 7-8 % on perfusion is expected: they energise two adjacent contacts on a
thermally insulated shaft, which concentrates heat relative to a lone sphere.

Why the absolute numbers looked irreconcilable before
-----------------------------------------------------
Their protocol is a **continuous 1.56 V RMS bipolar** drive between adjacent contacts
(their RMS reduction of a "high" clinical setting of 10 V, 185 pps, 210 us). Their peak
rise of 0.82 K corresponds to about 7.5 mW dissipated continuously, which at 1.56 V
implies roughly 325 ohm between the energised contacts -- a sensible bipolar impedance.

A duty-cycled *current*-controlled monopolar protocol at 3 mA, 60 us, 130 Hz dissipates
about 70 uW, roughly a hundredth of that, and correspondingly produces a rise of order
millikelvin. Both numbers are right; they describe different protocols. Compare power,
not amplitude.

Note on the source
------------------
This is the IEEE EMBS conference paper (Proc. 28th IEEE EMBS, New York, 2006,
pp. 3580-3583). The authors also published a longer treatment in J. Neural Eng. 3(4).
The values here are read from the conference paper, and ``references.elwassif2006``
cites it, not the journal article (ledger 75). The conference PDF prints no DOI.
"""

from __future__ import annotations

from dataclasses import dataclass

BASELINE_C = 37.0
"""Body core temperature; Table I reports absolute peak temperatures against this."""

V_RMS = 1.56
"""RMS voltage between the energised contacts, as the paper states it (p. 3581).

Transcribed as printed. It does not follow from the setting it is said to come from; see
:data:`RMS_OF_STATED_SETTING_V` (ledger 45)."""

RMS_QUOTE = (
    "We modeled a \u2018high\u2019 clinical DBS electrical setting (10 V, 185 pps and 210 μ "
    "sec) [21] using a constant Vrms of 1.56 Volt between the energized electrodes; "
    "Vrms was calculated from the root-mean-squared (r.m.s) voltage of the "
    "stimulation waveform."
)
"""p. 3581, as printed."""

RMS_OF_STATED_SETTING_V = 10.0 * (185.0 * 210e-6) ** 0.5
"""The RMS of the stated setting, 10 V pulses of 210 us at 185 pps: 1.971 V, not 1.56.

Recorded rather than "corrected" (ledger 45). The paper's own arithmetic is not
reproducible from what it states: a monophasic pulse gives 1.971 V, and a biphasic one
more. The package keeps 1.56 V, the number the paper's temperatures were computed at."""

IMPLIED_PULSE_WIDTH_US = (V_RMS / 10.0) ** 2 / 185.0 * 1e6
"""The pulse width at which 10 V and 185 pps would give 1.56 V RMS: about 131.5 us."""

CLINICAL_SETTING = "10 V, 185 pps, 210 us (Medtronic), reduced to 1.56 V RMS"

METABOLIC_HEAT_ASSUMED_ZERO = True
"""The authors state explicitly that Qm was set to zero in this paper."""


@dataclass(frozen=True)
class ThermalPoint:
    """One row of Table I: parameters in, peak temperature out."""

    sigma_S_per_m: float
    thermal_conductivity_W_per_mK: float
    perfusion_per_s: float
    t_max_C_lead_3389: float
    t_max_C_lead_3387: float

    @property
    def rise_K_3389(self) -> float:
        """Peak temperature rise above baseline for the 3389 lead."""
        return self.t_max_C_lead_3389 - BASELINE_C

    @property
    def rise_K_3387(self) -> float:
        """Peak temperature rise above baseline for the 3387 lead."""
        return self.t_max_C_lead_3387 - BASELINE_C


TABLE_I: tuple[ThermalPoint, ...] = (
    # Block I: electrical conductivity swept, kappa fixed, no perfusion
    ThermalPoint(0.15, 0.527, 0.0, 37.35, 37.21),
    ThermalPoint(0.20, 0.527, 0.0, 37.47, 37.28),
    ThermalPoint(0.30, 0.527, 0.0, 37.70, 37.42),
    ThermalPoint(0.35, 0.527, 0.0, 37.82, 37.48),
    # Block II: thermal conductivity swept, sigma fixed at 0.30, no perfusion
    ThermalPoint(0.30, 0.45, 0.0, 37.82, 37.48),
    ThermalPoint(0.30, 0.50, 0.0, 37.74, 37.44),
    ThermalPoint(0.30, 0.55, 0.0, 37.67, 37.40),
    ThermalPoint(0.30, 0.60, 0.0, 37.62, 37.37),
    # Block III: perfusion swept, sigma 0.30 and kappa 0.527 fixed
    ThermalPoint(0.30, 0.527, 0.000, 37.70, 37.42),
    ThermalPoint(0.30, 0.527, 0.004, 37.61, 37.34),
    ThermalPoint(0.30, 0.527, 0.008, 37.57, 37.31),
    ThermalPoint(0.30, 0.527, 0.012, 37.54, 37.29),
)

PEAK_RISE_K = 0.82
"""Largest rise anywhere in Table I, lead 3389, reached in two rows.

This is the "up to 0.8 C" quoted in the abstract. The row usually quoted is sigma 0.35
(the highest electrical conductivity swept) at kappa 0.527 and **zero** perfusion. The
thermal-conductivity block reaches the same 37.82 C at sigma 0.30 and kappa 0.45, its
lowest value (ledger 78, S-17: this said the 0.82 K row had "the lowest thermal
conductivity in the sweep", conflating the two).
"""

# --- the authors' stated tissue parameters ----------------------------------------

TISSUE_DENSITY_KG_PER_M3 = 1040.0
TISSUE_SPECIFIC_HEAT_J_PER_KGK = 3650.0
BLOOD_DENSITY_KG_PER_M3 = 1057.0
BLOOD_SPECIFIC_HEAT_J_PER_KGK = 3600.0
THERMAL_CONDUCTIVITY_RANGE_W_PER_MK = (0.45, 0.6)
"""Table I's sweep, 0.45-0.60 W/m/K (p. 3582). It was (0.5, 0.6), dropping 0.45, the
value that gives the block's hottest result (ledger 78, S-16)."""
CONDUCTIVITY_RANGE_S_PER_M = (0.15, 0.35)
PERFUSION_RANGE_PER_S = (0.004, 0.012)
"""Perfusion is tabulated in ml/s/ml, which is already a volumetric rate in 1/s."""

LEAD_3389_CONTACT_DIAMETER_UM = 1270.0
LEAD_3389_CONTACT_HEIGHT_UM = 1500.0
LEAD_3389_SPACING_UM = 500.0
LEAD_3387_SPACING_UM = 1500.0
"""Both leads use 1.5 mm contacts; the 3387 spaces them 1.5 mm apart, the 3389 0.5 mm.

The wider spacing of the 3387 is why it runs about 0.2 K cooler at matched settings.
"""

REFERENCE = "elwassif2006"


def conductivity_block() -> tuple[ThermalPoint, ...]:
    """Rows where only electrical conductivity varies."""
    return TABLE_I[0:4]


def thermal_conductivity_block() -> tuple[ThermalPoint, ...]:
    """Rows where only thermal conductivity varies."""
    return TABLE_I[4:8]


def perfusion_block() -> tuple[ThermalPoint, ...]:
    """Rows where only perfusion varies."""
    return TABLE_I[8:12]


def implied_power_W(
    rise_K: float = PEAK_RISE_K,
    thermal_conductivity_W_per_mK: float = 0.527,
    source_radius_m: float = 1.3803e-3,
) -> float:
    """Continuous power that the analytic unperfused solution needs for a given rise.

    Inverts ``dT = P / (4 pi kappa a)``. For their peak 0.82 K this returns about
    7.5 mW, which at 1.56 V RMS implies roughly 325 ohm between the energised contacts.
    """
    import math

    return (
        rise_K * 4.0 * math.pi * thermal_conductivity_W_per_mK * source_radius_m
    )
