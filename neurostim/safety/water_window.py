"""Water-window polarisation check.

The water window is the potential range between the reduction of water to hydrogen
(cathodic limit) and its oxidation to oxygen (anodic limit). Merrill et al. (2005):
once the electrode potential reaches either boundary, *all* further injected charge
goes into irreversible water electrolysis, because water is not mass-transport limited
in an aqueous medium.

Model used here
---------------
The interface is treated as a capacitance, so injecting a charge density produces

.. math::

    \\Delta V = \\frac{Q/A}{C_{eff}}

The question is what ``C_eff`` should be, and getting it wrong makes this check useless.

**Why the double-layer value alone is not usable.** Merrill et al.'s footnote 2 gives a
smooth-metal double-layer capacitance of 20 uF/cm^2. Using it for platinum predicts the
water window is reached at about 12 uC/cm^2 -- while Rose & Robblee *measured* that
platinum stays inside the window up to 100-150 uC/cm^2. That is a tenfold internal
contradiction between two numbers this package already holds, and it fired a false alarm
on essentially every realistic protocol.

The discrepancy is physical, not a bug: platinum and iridium oxide are pseudocapacitive.
Much of the injected charge goes into reversible surface reactions rather than charging
the double layer. Merrill quotes platinum's pseudocapacitance as 210 uC/cm^2 of real
area (Rand & Woods 1971), an order of magnitude above double-layer storage.

**What is done instead.** ``C_eff`` is derived from the material's own measured
charge-injection limit and window, so that injecting exactly the CIC brings the electrode
exactly to the window edge -- which is what the CIC *means*. The two numbers are then
consistent by construction rather than contradictory.

**What that leaves this check doing.** Not an independent test of charge density: the
charge-injection check already covers that, from the same measurement. What it adds is
the effect of anything that shifts the starting potential -- a non-zero resting
potential, or the interpulse bias several materials require to reach their quoted limit.
Those genuinely move the excursion and are not captured anywhere else. Supplying a
measured ``capacitance_uF_cm2`` overrides the derivation entirely.

The ohmic ``I * R_access`` drop across the tissue is *not* part of the electrode
potential and is excluded here; it belongs to the compliance-voltage calculation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..materials import Material, WaterWindow, get_material

DOUBLE_LAYER_CAPACITANCE_uF_cm2 = 20.0
"""Canonical smooth-metal double-layer capacitance (Merrill et al. 2005, footnote 2)."""


def effective_capacitance_uF_cm2(
    material: Material | str, *, anodic_first: bool | None = None
) -> float:
    """Interfacial capacitance implied by a material's own CIC and water window.

    Defined so that injecting the charge-injection limit brings the electrode exactly to
    the window edge, which is the definition of that limit. Falls back to the
    double-layer value when the material has no window on record.

    For platinum this returns 250 uF/cm^2 rather than 20, an order of magnitude above
    double-layer storage and consistent with its known pseudocapacitance.
    """
    mat = material if isinstance(material, Material) else get_material(material)
    if mat.water_window is None:
        return DOUBLE_LAYER_CAPACITANCE_uF_cm2
    # The CIC is the charge that just reaches the window edge, so the widest measured
    # value defines the excursion per coulomb.
    limit = mat.cic_uC_cm2("optimistic", anodic_first)
    # Use the half-window the leading phase actually swings toward. An anodic-first
    # pulse drives the electrode positive and is bounded by the anodic limit; a
    # cathodic-first pulse by the cathodic one. Windows are not symmetric, so this
    # matters. With polarity unknown, take the narrower half.
    if anodic_first is True:
        available_V = abs(mat.water_window.anodic_V)
    elif anodic_first is False:
        available_V = abs(mat.water_window.cathodic_V)
    else:
        available_V = min(
            abs(mat.water_window.cathodic_V), abs(mat.water_window.anodic_V)
        )
    if available_V <= 0:  # pragma: no cover - windows always straddle zero here
        return DOUBLE_LAYER_CAPACITANCE_uF_cm2
    return limit / available_V


def validate_resting_potential_V(
    material: Material | str, resting_potential_V: float
) -> None:
    """Raise unless the electrode is inside its own window before any current flows.

    Two things go wrong when it is not, and the second is the reason this is a rejection
    rather than a caveat.

    The visible one is that the answers stop meaning anything:
    ``max_charge_density_in_window_uC_cm2("Pt", resting_potential_V=5.0)`` used to report
    1400 uC/cm^2 "allowed" for an interface already 4.2 V past its anodic limit at rest
    (ledger 14). The negative direction was caught only incidentally, by the
    ``available_V <= 0`` guard.

    The structural one is that the water-window verdict stops being monotone in current.
    From outside the anodic limit a small cathodic pulse pulls the interface back INTO the
    window while a large one breaches it on the other side, so the check reads FAIL, PASS,
    FAIL as amplitude rises. Every reported limit in this package is produced by
    "the largest value that still passes", which is the wrong question for a predicate
    with two boundaries -- and it is the precondition ``_limits.floor_to_pass`` declares
    and asserts. Phase 0b measured the scope: over 1824 swept configurations *every*
    non-monotone case was an out-of-window resting potential, and across 630 in-window
    configurations there were none. Rejecting the input makes the precondition true rather
    than merely asserted.

    A material with no window on record is not validated: there is nothing to be outside
    of, and the check reports NOT_EVALUATED.

    Inclusive at both ends, matching :meth:`WaterWindow.contains`, so the rejection cannot
    disagree with the check it protects about the boundary itself.
    """
    if not math.isfinite(resting_potential_V):
        raise ValueError(
            f"resting_potential_V must be finite, got {resting_potential_V!r}"
        )
    mat = material if isinstance(material, Material) else get_material(material)
    window = mat.water_window
    if window is None or window.contains(resting_potential_V):
        return
    raise ValueError(
        f"resting_potential_V = {resting_potential_V:g} V is outside {mat.key}'s water "
        f"window [{window.cathodic_V:g}, {window.anodic_V:g}] V ({window.scale}). "
        f"An electrode already outside its window at rest is in irreversible "
        f"electrolysis before the pulse begins, so no charge-injection limit computed "
        f"here applies to it; and the water-window verdict is then non-monotone in "
        f"current, which every reported limit in this package assumes it is not. "
        f"Supply the electrode's measured open-circuit potential on the window's own "
        f"scale."
    )


def polarisation_V(
    charge_density_uC_cm2: float,
    capacitance_uF_cm2: float = DOUBLE_LAYER_CAPACITANCE_uF_cm2,
) -> float:
    """Potential excursion from charging a double layer, in volts.

    ``uC/cm^2`` divided by ``uF/cm^2`` gives volts directly.
    """
    if not math.isfinite(capacitance_uF_cm2) or capacitance_uF_cm2 <= 0:
        raise ValueError(
            f"capacitance_uF_cm2 must be finite and > 0, got {capacitance_uF_cm2!r}"
        )
    return charge_density_uC_cm2 / capacitance_uF_cm2


@dataclass(frozen=True)
class WaterWindowResult:
    """Outcome of the water-window check for one phase of a pulse."""

    material_key: str
    window: WaterWindow | None
    resting_potential_V: float
    excursion_V: float
    peak_potential_V: float
    polarity: str
    capacitance_uF_cm2: float
    interface_model: str = "capacitance derived from the material's own CIC and window"

    @property
    def evaluated(self) -> bool:
        """Whether a water window was available for this material at all."""
        return self.window is not None

    @property
    def passes(self) -> bool:
        """Whether the peak potential stayed inside the window.

        Returns ``True`` when no window is on record -- the check did not fail, it did
        not run. Read :attr:`evaluated` alongside this.
        """
        if self.window is None:
            return True
        return self.window.contains(self.peak_potential_V)

    @property
    def headroom_V(self) -> float:
        """Volts remaining before the relevant window boundary is reached."""
        if self.window is None:
            return math.inf
        if self.polarity == "anodic":
            return self.window.anodic_V - self.peak_potential_V
        return self.peak_potential_V - self.window.cathodic_V

    def describe(self) -> str:
        """Multi-line summary."""
        if self.window is None:
            return (
                f"Water window ({self.material_key}) -> NOT EVALUATED\n"
                f"  no potential limits on record for this material in the cited source"
            )
        verdict = "PASS" if self.passes else "EXCEEDS"
        return "\n".join(
            [
                f"Water window ({self.material_key}, {self.polarity} phase) -> {verdict}",
                f"  window        {self.window.describe()}",
                f"  rest -> peak  {self.resting_potential_V:+.3f} V -> "
                f"{self.peak_potential_V:+.3f} V "
                f"(excursion {self.excursion_V:.3f} V)",
                f"  headroom      {self.headroom_V:+.3f} V",
                f"  interface     {self.interface_model}, "
                f"C_dl = {self.capacitance_uF_cm2:g} uF/cm^2",
            ]
        )


def evaluate(
    material: Material | str,
    charge_density_uC_cm2: float,
    *,
    anodic_first: bool = False,
    resting_potential_V: float = 0.0,
    capacitance_uF_cm2: float | None = None,
    anodic_first_for_capacitance: bool | None = None,
) -> WaterWindowResult:
    """Check whether the leading phase drives the electrode out of the water window.

    Parameters
    ----------
    resting_potential_V:
        Open-circuit electrode potential versus Ag|AgCl before the pulse. Defaults to
        0 V, which sits near the middle of the Pt/IrOx window. A real electrode's
        resting potential depends on its history and on any applied interpulse bias --
        several materials in the database reach their quoted charge-injection limit
        *only* under a positive bias, which this parameter is how you represent.

        Must lie inside the material's own window; a value outside it raises
        ``ValueError``. See :func:`validate_resting_potential_V`.
    """
    mat = material if isinstance(material, Material) else get_material(material)
    validate_resting_potential_V(mat, resting_potential_V)
    if capacitance_uF_cm2 is None:
        capacitance_uF_cm2 = effective_capacitance_uF_cm2(
            mat, anodic_first=anodic_first_for_capacitance
        )
    excursion = polarisation_V(charge_density_uC_cm2, capacitance_uF_cm2)
    polarity = "anodic" if anodic_first else "cathodic"
    sign = 1.0 if anodic_first else -1.0
    peak = resting_potential_V + sign * excursion

    return WaterWindowResult(
        material_key=mat.key,
        window=mat.water_window,
        resting_potential_V=resting_potential_V,
        excursion_V=excursion,
        peak_potential_V=peak,
        polarity=polarity,
        capacitance_uF_cm2=capacitance_uF_cm2,
    )


def max_charge_density_in_window_uC_cm2(
    material: Material | str,
    *,
    anodic_first: bool = False,
    resting_potential_V: float = 0.0,
    capacitance_uF_cm2: float | None = None,
) -> float:
    """Charge density that just reaches the window boundary under the capacitive model.

    Returns ``inf`` when the material has no window on record. Raises ``ValueError`` when
    ``resting_potential_V`` is outside the material's window -- this function used to
    answer 1400 uC/cm^2 "allowed" for a platinum interface resting 4.2 V past its anodic
    limit (ledger 14). See :func:`validate_resting_potential_V`.
    """
    mat = material if isinstance(material, Material) else get_material(material)
    validate_resting_potential_V(mat, resting_potential_V)
    if mat.water_window is None:
        return math.inf
    if capacitance_uF_cm2 is None:
        # Polarity-specific: Rose & Robblee define both platinum limits by the same
        # window criterion, so a different charge density reaches it depending on which
        # reactions the leading phase can access. The capacitance follows suit.
        capacitance_uF_cm2 = effective_capacitance_uF_cm2(
            mat, anodic_first=anodic_first
        )
    if anodic_first:
        available_V = mat.water_window.anodic_V - resting_potential_V
    else:
        available_V = resting_potential_V - mat.water_window.cathodic_V
    if available_V <= 0:
        return 0.0
    return available_V * capacitance_uF_cm2
