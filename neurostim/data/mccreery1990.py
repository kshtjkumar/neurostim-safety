"""The McCreery et al. (1990) histology dataset that the Shannon criterion is fitted to.

Transcribed from Table I of the primary paper. This is the evidence behind the damage
separatrix: without it the Shannon line is an assertion, and a safe-operating-area plot
that draws the line without the points is not showing the reader anything they can check.

Experimental conditions -- every point shares them
--------------------------------------------------
- Adult cat, parietal cortex, electrodes implanted at least 10 days before pulsing
- Charge-balanced, current-regulated, symmetric pulse pairs, **anodic first**
- **400 us per phase**, **50 Hz**, **7 h continuous**
- Perfused within 20 min of the end of stimulation; graded blind at light-microscope level
- Surface electrodes are platinum discs (0.01-0.5 cm^2) on polyester mesh, current
  directed out one face only
- Penetrating electrodes are activated iridium, 6.5 +/- 3 x 10^-5 cm^2, conical tip

What the authors say the data do and do not establish
-----------------------------------------------------
The threshold is not a single charge density. Quoting the discussion: at 1 uC per phase
the damage threshold lies between 50 and 100 uC/cm^2, but at 5 uC per phase it falls to
between 10 and 12 uC/cm^2. Charge density and charge per phase are *cofactors*.

The authors also state three limits explicitly: light microscopy would not detect subtler
morphologic change; stimulus frequency and total pulse count matter and were held fixed
here; and many neurons scored as damaged recover within seven days.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Outcome = Literal["none", "partial", "damage"]
"""``partial`` means some sites at that condition were damaged and others were not."""

Severity = Literal["none", "minimal", "mild", "moderate", "severe"]


@dataclass(frozen=True)
class DamagePoint:
    """One experimental condition from Table I."""

    area_cm2: float
    charge_density_uC_cm2: float
    charge_per_phase_uC: float
    n_animals: int
    n_sites: int
    outcome: Outcome
    worst_severity: Severity
    electrode: str
    note: str = ""

    @property
    def shannon_k(self) -> float:
        """The Shannon metric ``log10(Q) + log10(Q/A)`` at this point."""
        import math

        return math.log10(self.charge_per_phase_uC) + math.log10(
            self.charge_density_uC_cm2
        )


# Table I. Unpulsed control rows are omitted: all 23 control sites showed no damage,
# which is recorded in CONTROL_SITES rather than as points on a charge/charge-density
# plane where they have no coordinates.
TABLE_I: tuple[DamagePoint, ...] = (
    # --- penetrating activated-iridium microelectrodes ---
    DamagePoint(
        area_cm2=6.5e-5,
        charge_density_uC_cm2=800.0,
        charge_per_phase_uC=0.05,
        n_animals=3,
        n_sites=6,
        outcome="none",
        worst_severity="none",
        electrode="iridium penetrating microelectrode",
        note=(
            "No damage despite the highest charge density in the study. Some "
            "mononuclear leukocyte infiltration adjacent to the tip."
        ),
    ),
    DamagePoint(
        area_cm2=6.5e-5,
        charge_density_uC_cm2=1600.0,
        charge_per_phase_uC=0.1,
        n_animals=1,
        n_sites=4,
        outcome="none",
        worst_severity="none",
        electrode="iridium penetrating microelectrode",
        note="Highest charge density tested anywhere in the study; no damage.",
    ),
    # --- platinum surface discs ---
    DamagePoint(
        area_cm2=0.01,
        charge_density_uC_cm2=100.0,
        charge_per_phase_uC=1.0,
        n_animals=1,
        n_sites=4,
        outcome="partial",
        worst_severity="moderate",
        electrode="platinum surface disc",
        note=(
            "3 of 4 sites mild to moderate. A companion study with identical "
            "electrodes and conditions found damage under 16 of 17 electrodes at "
            "1 uC/ph and 100 uC/cm^2, or 0.88 uC/ph and 88 uC/cm^2."
        ),
    ),
    DamagePoint(
        area_cm2=0.02,
        charge_density_uC_cm2=50.0,
        charge_per_phase_uC=1.0,
        n_animals=3,
        n_sites=6,
        outcome="partial",
        worst_severity="moderate",
        electrode="platinum surface disc",
        note="5 of 6 sites undamaged, 1 moderate.",
    ),
    DamagePoint(
        area_cm2=0.10,
        charge_density_uC_cm2=10.0,
        charge_per_phase_uC=1.0,
        n_animals=5,
        n_sites=9,
        outcome="none",
        worst_severity="none",
        electrode="platinum surface disc",
    ),
    DamagePoint(
        area_cm2=0.5,
        charge_density_uC_cm2=10.0,
        charge_per_phase_uC=5.0,
        n_animals=3,
        n_sites=3,
        outcome="none",
        worst_severity="none",
        electrode="platinum surface disc",
    ),
    DamagePoint(
        area_cm2=0.5,
        charge_density_uC_cm2=12.0,
        charge_per_phase_uC=6.0,
        n_animals=3,
        n_sites=3,
        outcome="partial",
        worst_severity="minimal",
        electrode="platinum surface disc",
        note="2 sites minimal damage, 1 undamaged. The lowest charge density at "
        "which any damage was seen in the study.",
    ),
    DamagePoint(
        area_cm2=0.5,
        charge_density_uC_cm2=16.0,
        charge_per_phase_uC=8.0,
        n_animals=2,
        n_sites=2,
        outcome="damage",
        worst_severity="moderate",
        electrode="platinum surface disc",
        note="mild to moderate",
    ),
    DamagePoint(
        area_cm2=0.5,
        charge_density_uC_cm2=20.0,
        charge_per_phase_uC=10.0,
        n_animals=1,
        n_sites=1,
        outcome="damage",
        worst_severity="moderate",
        electrode="platinum surface disc",
        note="mild to moderate",
    ),
    DamagePoint(
        area_cm2=0.5,
        charge_density_uC_cm2=25.0,
        charge_per_phase_uC=12.5,
        n_animals=1,
        n_sites=1,
        outcome="damage",
        worst_severity="moderate",
        electrode="platinum surface disc",
    ),
    DamagePoint(
        area_cm2=0.5,
        charge_density_uC_cm2=30.0,
        charge_per_phase_uC=15.0,
        n_animals=1,
        n_sites=1,
        outcome="damage",
        worst_severity="severe",
        electrode="platinum surface disc",
        note="moderate to severe",
    ),
    DamagePoint(
        area_cm2=0.5,
        charge_density_uC_cm2=36.0,
        charge_per_phase_uC=18.0,
        n_animals=1,
        n_sites=1,
        outcome="damage",
        worst_severity="severe",
        electrode="platinum surface disc",
        note="moderate to severe",
    ),
)

CONTROL_SITES = 23
"""Unpulsed control sites examined; all showed no damage."""

TOTAL_SITES_EXAMINED = 64
"""Sites examined at the light-microscope level, from 22 animals; 41 were pulsed."""

PULSE_WIDTH_US = 400.0
"""Every point was collected at 400 us per phase."""

FREQUENCY_HZ = 50.0
"""Every point was collected at 50 Hz."""

DURATION_H = 7.0
"""Every point was collected after 7 h of continuous stimulation."""

REFERENCE = "mccreery1990"


def damaged() -> tuple[DamagePoint, ...]:
    """Conditions where damage occurred at every site."""
    return tuple(p for p in TABLE_I if p.outcome == "damage")


def undamaged() -> tuple[DamagePoint, ...]:
    """Conditions where no site was damaged."""
    return tuple(p for p in TABLE_I if p.outcome == "none")


def partial() -> tuple[DamagePoint, ...]:
    """Conditions where some sites were damaged and others were not."""
    return tuple(p for p in TABLE_I if p.outcome == "partial")


def separating_k_range() -> tuple[float, float]:
    """The band of Shannon ``k`` between the highest safe and lowest damaging point.

    Any separatrix has to fall inside this band to be consistent with the data. It is
    computed from the surface-electrode points only: the penetrating iridium
    microelectrodes sit at extreme charge density with no damage and, as the authors
    note, the tissue actually adjacent to them experiences a lower local charge density
    than the geometric figure implies.
    """
    surface = [p for p in TABLE_I if "surface" in p.electrode]
    safe = max(p.shannon_k for p in surface if p.outcome == "none")
    hurt = min(p.shannon_k for p in surface if p.outcome in ("damage", "partial"))
    return (safe, hurt)


def local_charge_density_uC_cm2(
    surface_charge_density_uC_cm2: float,
    distance_um: float,
    electrode_radius_um: float,
) -> float:
    """On-axis charge density at a depth below a disc electrode, McCreery eq. (1).

    ``QD_x = QD_s * (1 - x / sqrt(R^2 + x^2))``

    This is why a microelectrode at 800 uC/cm^2 can leave neurons intact: the charge
    density falls steeply with distance, and no neuron sits at the surface. The authors
    note the formula assumes uniform current density over the facet, whereas real discs
    concentrate current at the perimeter, so it *under*-estimates the local density a
    short way out.
    """
    import math

    if electrode_radius_um <= 0:
        raise ValueError(
            f"electrode_radius_um must be > 0, got {electrode_radius_um!r}"
        )
    if distance_um < 0:
        raise ValueError(f"distance_um must be >= 0, got {distance_um!r}")
    attenuation = 1.0 - distance_um / math.sqrt(
        electrode_radius_um**2 + distance_um**2
    )
    return surface_charge_density_uC_cm2 * attenuation
