"""Tantalum-pentoxide capacitor electrodes, read from the two papers Cogan cites.

Why this module exists
----------------------
Cogan (2008) Table 2 gives Ta2O5 a single number -- "~0.5" mC/cm^2 -- with no pulse
width and no potential limits, citing Rose et al. (1985) and Schmidt et al. (1982).
Merrill (2005) Table 2 gives two different geometric charge storage capacities, 700 and
200 uC/cm^2, also unconditioned. Three numbers spanning more than threefold, none of
them reproducible from what the reviews print.

Reading both primary papers resolves it, and the resolution is that **a capacitor
electrode has no material charge-injection limit at all**. Its limit is a design
parameter:

.. math::

    \\frac{Q}{A} = C \\times 0.8 V_f, \\qquad C = \\frac{k \\epsilon_0 A_e}{d},
    \\qquad d \\propto V_f

Charge storage is set by the real-to-geometric area ratio and the anodisation forming
voltage, not by any electrochemistry of the material. Every value below is one electrode
design, and they range over a factor of 80.

The film-thickness relation, and why it matters
-----------------------------------------------
For an anodically grown film the thickness varies directly with the forming voltage, so
the charge stored at a fixed *fraction* of ``V_f`` is independent of thickness -- storage
can only be raised by roughening the surface or by a higher-permittivity dielectric.

This is checkable against the paper's own arithmetic. Rose et al. report smooth Ta at
22 nF/mm^2 for a **5 V** film, and etched Ta anodised to **10 V** at 0.13-0.33 uF/mm^2,
which they call an enhancement of "12 to 30". Those two statements are consistent only if
the smooth baseline is thickness-corrected to 10 V first: 22 / 2 = 11 nF/mm^2, and
130/11 = 12, 330/11 = 30. Comparing against the uncorrected 22 nF/mm^2 would give 6 to 15
and contradict the paper. :func:`smooth_capacitance_nF_mm2` implements the correction.

The safe operating voltage
--------------------------
Not a water window. For an anodic film the ceiling is dielectric breakdown, at which the
film becomes an electronic conductor, and the safe value is about **80 % of the forming
voltage**. Two further operating constraints are stated rather than derived: DC leakage
current should not exceed 1-10 nA, and excursions of 10 V or less are "generally
considered acceptable" -- both because the film is an insulator being asked not to
conduct, which has no analogue in a faradaic electrode.

The conclusion the authors drew
-------------------------------
Rose et al. set the target for intracortical single-neuron stimulation at 5 nC in a
0.2 ms pulse. On the 0.5e-6 cm^2 electrode "as used by Schmidt and McIntosh", which is
where their densities come from (p. 182), that is 10,000 uC/cm^2 and 50 A/cm^2. On the
1e-4 mm^2 (1e-6 cm^2) electrode of their Table III it is 5,000 uC/cm^2 and 25 A/cm^2
(ledger 78, S-15: this sentence used to give the first pair for the second area). Scaling
their best measured designs down to that area gives 0.26 nC for Ta/Ta2O5 and 0.63 nC for
Ti/TiO2 -- one to two orders of magnitude short. Their verdict was that capacitor
electrodes are not competitive with activated iridium at microelectrode scale, and the
field went that way.

Units note
----------
Both papers work in uC/mm^2. This module keeps their units and provides
:func:`to_uC_per_cm2` rather than silently converting, so any value here can be found
verbatim in the source text.
"""

from __future__ import annotations

from dataclasses import dataclass

REFERENCES = ("rose1985_capacitor", "schmidt1982_capacitor")

DIELECTRIC_CONSTANT_TA2O5 = 25.0
"""Relative permittivity of anodically formed Ta2O5 (Rose et al. 1985)."""

DIELECTRIC_CONSTANT_TIO2_RUTILE = 100.0
DIELECTRIC_CONSTANT_TIO2_ANATASE = 50.0
"""TiO2 offers 2-4x the permittivity of Ta2O5, at 1-2 orders more leakage current."""

SAFE_FRACTION_OF_FORMING_VOLTAGE = 0.8
"""Fraction of the anodisation voltage an anodic film can safely be pulsed to."""

SMOOTH_TA_CAPACITANCE_NF_MM2_AT_5V = 22.0
"""Measured capacitance of a 5 V Ta2O5 film on smooth tantalum, in nF/mm^2."""

MAX_LEAKAGE_CURRENT_NA = 10.0
"""Upper end of the accepted DC leakage band (1-10 nA) during operation."""

MAX_ACCEPTABLE_EXCURSION_V = 10.0
"""Pulse excursion "generally considered acceptable" for a capacitor electrode."""

INTRACORTICAL_TARGET_CHARGE_NC = 5.0
INTRACORTICAL_TARGET_PULSE_WIDTH_US = 200.0
INTRACORTICAL_TARGET_AREA_MM2 = 1e-4
"""The single-neuron stimulation target Rose et al. measured every design against."""

PORE_RESISTANCE_MAX_REDUCTION = 0.8
"""Fraction by which pulsed capacitance can fall below the slow-charged value.

Electrolyte conductivity inside the pores of a roughened electrode limits how fast it
charges, so a short pulse reaches only part of the DC capacitance. Rose et al. put the
worst case at 80 % lost. This is the mechanism that makes the *pulsed* charge storage of
etched Ta (0.88-1.4 uC/mm^2 at 0.1 ms) fall below its DC value (1.04-2.64 uC/mm^2).
"""


@dataclass(frozen=True)
class CapacitorElectrode:
    """One published capacitor-electrode design and what it stored."""

    label: str
    dielectric: str
    preparation: str
    charge_storage_uC_mm2: float
    reference: str
    geometric_area_mm2: float | None = None
    forming_voltage_V: float | None = None
    pulse_width_us: float | None = None
    note: str = ""

    @property
    def charge_storage_uC_cm2(self) -> float:
        """The same value in the units the rest of this package uses."""
        return to_uC_per_cm2(self.charge_storage_uC_mm2)

    @property
    def safe_operating_voltage_V(self) -> float | None:
        """80 % of the forming voltage, where one is on record."""
        if self.forming_voltage_V is None:
            return None
        return safe_operating_voltage_V(self.forming_voltage_V)

    def scaled_to_microelectrode_nC(
        self, area_mm2: float = INTRACORTICAL_TARGET_AREA_MM2
    ) -> float:
        """Charge this design would deliver if its storage density held at ``area_mm2``.

        This is the extrapolation in Rose et al.'s Table III, and it is optimistic by
        their own admission: the roughness factors behind the best densities have never
        been achieved on electrodes that small, because polishing rather than etching
        takes place on very small areas.
        """
        return self.charge_storage_uC_mm2 * area_mm2 * 1e3


DESIGNS: tuple[CapacitorElectrode, ...] = (
    CapacitorElectrode(
        label="smooth Ta",
        dielectric="Ta2O5",
        preparation="anodised, no surface enhancement",
        charge_storage_uC_mm2=0.088,
        forming_voltage_V=5.0,
        reference="rose1985_capacitor",
        note=(
            "22 nF/mm^2 at 4 V, the baseline every roughness factor is measured "
            "against. 8.8 uC/cm^2 -- two orders of magnitude below Cogan's ~0.5 mC/cm^2"
        ),
    ),
    CapacitorElectrode(
        label="roughened Ta wire (Schaldach 1971)",
        dielectric="Ta2O5",
        preparation="roughened tip of a 2 mm anodised Ta wire, cardiac pacing",
        charge_storage_uC_mm2=1.5,
        forming_voltage_V=2.5,
        reference="rose1985_capacitor",
        note="Quoted at a 2 V breakdown voltage rather than at 80 % of forming",
    ),
    CapacitorElectrode(
        label="sintered porous disc (Guyton & Hambrecht 1973/74)",
        dielectric="Ta2O5",
        preparation="anodised sintered porous tantalum disc, surface stimulation",
        charge_storage_uC_mm2=7.0,
        reference="rose1985_capacitor",
        note=(
            "700 uC/cm^2 at 80 % of forming voltage. This is the source of the 700 "
            "uC/cm^2 in Merrill 2005 Table 2, and it is a macroelectrode for surface "
            "stimulation -- not an intracortical value"
        ),
    ),
    CapacitorElectrode(
        label="sintered Ta microelectrode (Lerner et al. 1982)",
        dielectric="Ta2O5",
        preparation=(
            "Ta-particle slurry on 0.08 mm wire, fired at 1600 C in vacuum, "
            "anodised to 5 V in 0.015 M H2SO4"
        ),
        charge_storage_uC_mm2=1.5,
        geometric_area_mm2=0.26,
        forming_voltage_V=5.0,
        pulse_width_us=100.0,
        reference="rose1985_capacitor",
        note=(
            "0.10 +/- 0.01 uF measured with pulses as short as 100 us; area "
            "enhancement about 17x. At 50 us the effective capacitance fell to 80 % "
            "of its maximum. This is the electrode Schmidt et al. implanted"
        ),
    ),
    CapacitorElectrode(
        label="etched Ta microelectrode, pulsed (Robblee et al. 1983c)",
        dielectric="Ta2O5",
        preparation=(
            "electrolytically etched cone tip, anodised to 10 V vs SCE in "
            "0.1 vol% H3PO4"
        ),
        charge_storage_uC_mm2=0.88,
        geometric_area_mm2=0.12,
        forming_voltage_V=10.0,
        pulse_width_us=100.0,
        reference="rose1985_capacitor",
        note=(
            "Low end of a measured 0.88-1.4 uC/mm^2 band at 0.1 ms and 80 % of "
            "forming voltage. Capacitance 0.13-0.33 uF/mm^2, enhancement 12-30x. "
            "Leakage about 2 nA at 8 V; 200 h in protein-saline caused no degradation. "
            "Never tested in vivo"
        ),
    ),
    CapacitorElectrode(
        label="etched Ta, best reported (Rose et al. 1985 Table III)",
        dielectric="Ta2O5",
        preparation="etched Ta wire, best value in their comparison table",
        charge_storage_uC_mm2=2.6,
        geometric_area_mm2=0.057,
        # No pulse width (ledger 77, S-11): Table III's "Highest charge density" column,
        # p. 191; its "200 us constant current pulse" belongs to the theoretical last
        # column, not to how this value was measured.
        reference="rose1985_capacitor",
        note=(
            "260 uC/cm^2, the highest charge density they report for any Ta2O5 "
            "electrode (Table III, p. 191), and still about half of Cogan's ~0.5 "
            "mC/cm^2. Consistent with the DC capacitance (0.33 uF/mm^2 x 8 V = 2.64) "
            "rather than with the pulsed value, so it is a slow-charge figure; the "
            "table's 200 us belongs to its theoretical last column"
        ),
    ),
    CapacitorElectrode(
        label="etched Ti, best reported (Wong & Lerner 1983b)",
        dielectric="TiO2",
        preparation="Ti wire etched at 55 C, DC anodised in 0.015 M H2SO4",
        charge_storage_uC_mm2=6.3,
        geometric_area_mm2=0.27,
        # No pulse width (S-11): measured on an AC capacitance bridge, Table I, p. 187.
        reference="rose1985_capacitor",
        note=(
            "Measured on an AC capacitance bridge, not with pulses: Table I (p. 187) "
            "lists its capacitance as '1570 (AC)', and footnote d reads 'AC indicates "
            "measurement made with capacitance bridge'. The highest density in their "
            "Table III comparison of microelectrode designs (p. 191), bought at 0.4 "
            "nA/nF leakage. TiO2 raises storage by 'a factor of as much as 4 relative to "
            "Ta based electrodes' (p. 186); their Table III gives 6.3 against 2.6 "
            "uC/mm^2 (2.4x) at 0.10 against 0.07 nA/nF lowest leakage (1.4x). Only the "
            "Guyton & "
            "Hambrecht surface macroelectrode stores more, and it is not intracortical"
        ),
    ),
    CapacitorElectrode(
        label="sputtered BaTiO3 on Pt",
        dielectric="BaTiO3",
        preparation="rf-sputtered 1.0 um film, annealed 1200 C for 6 h",
        charge_storage_uC_mm2=0.07,
        geometric_area_mm2=100.0,
        reference="rose1985_capacitor",
        note=(
            "Effective dielectric constant 7000 from the porous annealed structure, "
            "but the pores expose bare Pt, so the film can only be charged to 1.0-1.2 V "
            "before oxygen evolves on the substrate. High permittivity does not survive "
            "contact with an electrolyte"
        ),
    ),
)

IN_VIVO_CHARGE_DENSITY_UC_MM2 = 0.94
IN_VIVO_CURRENT_DENSITY_MA_MM2 = 1.3
"""Highest densities Bernstein/Johnson et al. (1977) drove porous Ta discs to in vivo.

Their comparison protocol was 0.5 ms at 50 Hz and 3.8 mA/mm^2 geometric, and they
concluded Ta/Ta2O5 produced less tissue damage than metal or carbon electrodes at
matched parameters.
"""

# --- Schmidt et al. (1982): the only in vivo intracortical test -------------------

SCHMIDT_PULSE_WIDTH_US = 100.0
SCHMIDT_PULSE_RATE_HZ = 400.0
SCHMIDT_PULSES_PER_TRAIN = 17
SCHMIDT_TRAIN_INTERVAL_S = 2.0
SCHMIDT_ANODIC_BIAS_V = 4.2
SCHMIDT_THRESHOLD_UA = 35.0
SCHMIDT_IMPLANT_DAYS = 57
SCHMIDT_TIP_EXPOSURE_UM = 500.0
SCHMIDT_MAX_DIAMETER_UM = 190.0

CAPACITOR_REQUIRES_ANODIC_BIAS = True
"""A capacitor electrode can only be pulsed cathodically from an anodic bias.

The film charges in one direction only, so cathodic pulses -- which Stoney et al. showed
are the more effective ones for PT cells -- require biasing the electrode positive first.
Schmidt et al. held +4.2 V DC and pulsed down from it, and measured thresholds up to
44.5 % lower than with anodic pulsing. Any protocol built on this material inherits a
standing DC bias, and with it a standing leakage current.
"""

SCHMIDT_THREE_ELEMENT_TRANSIENT = (
    "access resistance",
    "lumped pore resistance",
    "lumped capacitance",
)
"""What Schmidt et al. extracted from a single 100 uA, 0.1 ms pulse.

:mod:`neurostim.transient` separates a measured pulse into two parts, an ohmic access
voltage and an interfacial polarisation. That is the right decomposition for a smooth
electrode and one term short for a porous one: the electrolyte inside the pores adds a
resistance in series with the interface, which appears in the trace as a slower ohmic
component and will otherwise be absorbed into the polarisation. Expect
:func:`neurostim.transient.analyse` to overstate polarisation, and so understate the
charge-injection limit, on sintered, etched or otherwise porous electrodes.
"""


def to_uC_per_cm2(uC_per_mm2: float) -> float:
    """Convert the papers' units to this package's. 1 mm^2 = 0.01 cm^2."""
    return uC_per_mm2 * 100.0


def safe_operating_voltage_V(forming_voltage_V: float) -> float:
    """Highest potential an anodic film should be pulsed to: 80 % of forming voltage.

    This replaces the water window for a capacitor electrode. It is a property of how
    the film was grown, not of the material, which is why :mod:`neurostim.materials`
    records no window for Ta2O5.
    """
    if forming_voltage_V <= 0:
        raise ValueError(
            f"forming_voltage_V must be > 0, got {forming_voltage_V!r}"
        )
    return SAFE_FRACTION_OF_FORMING_VOLTAGE * forming_voltage_V


def smooth_capacitance_nF_mm2(forming_voltage_V: float) -> float:
    """Capacitance of a smooth Ta2O5 film grown at ``forming_voltage_V``.

    Film thickness varies directly with forming voltage and capacitance goes as 1/d, so
    the 22 nF/mm^2 measured at 5 V scales as ``22 * 5 / V_f``. Use this as the baseline
    when computing a roughness factor, or the answer will be wrong by ``V_f / 5``.
    """
    if forming_voltage_V <= 0:
        raise ValueError(
            f"forming_voltage_V must be > 0, got {forming_voltage_V!r}"
        )
    return SMOOTH_TA_CAPACITANCE_NF_MM2_AT_5V * 5.0 / forming_voltage_V


def roughness_factor(
    measured_capacitance_uF_mm2: float, forming_voltage_V: float
) -> float:
    """Real-to-geometric area ratio implied by a measured capacitance.

    Reproduces the "12 to 30" Rose et al. quote for etched Ta anodised to 10 V from
    their measured 0.13-0.33 uF/mm^2.
    """
    if measured_capacitance_uF_mm2 <= 0:
        raise ValueError(
            f"measured_capacitance_uF_mm2 must be > 0, "
            f"got {measured_capacitance_uF_mm2!r}"
        )
    baseline_uF_mm2 = smooth_capacitance_nF_mm2(forming_voltage_V) * 1e-3
    return measured_capacitance_uF_mm2 / baseline_uF_mm2


def charge_storage_uC_mm2(
    capacitance_uF_mm2: float, forming_voltage_V: float
) -> float:
    """``Q/A = C x 0.8 V_f`` -- the whole model for a capacitor electrode."""
    return capacitance_uF_mm2 * safe_operating_voltage_V(forming_voltage_V)


def parallel_plate_capacitance_F(
    dielectric_constant: float, area_m2: float, thickness_m: float
) -> float:
    """``C = k eps0 A / d``, Rose et al. equation (1).

    Reproduces their worked case: a 10 nm BaTiO3 film of dielectric constant 7000 on a
    1e-4 mm^2 electrode pulsed to 4 V stores about 2.4 nC.
    """
    if thickness_m <= 0 or area_m2 <= 0 or dielectric_constant <= 0:
        raise ValueError("dielectric constant, area and thickness must all be > 0")
    vacuum_permittivity = 8.854e-12
    return dielectric_constant * vacuum_permittivity * area_m2 / thickness_m


def meets_intracortical_target(design: CapacitorElectrode) -> bool:
    """Whether a design delivers 5 nC on a 1e-4 mm^2 electrode. None of them do."""
    return design.scaled_to_microelectrode_nC() >= INTRACORTICAL_TARGET_CHARGE_NC


def best_design() -> CapacitorElectrode:
    """The highest charge storage in the review, for any dielectric."""
    return max(DESIGNS, key=lambda d: d.charge_storage_uC_mm2)
