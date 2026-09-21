"""Stimulator compliance voltage.

A constant-current stimulator can only hold its commanded current while it has enough
voltage headroom to push that current through the total series impedance. When the
required voltage exceeds the compliance voltage the current source drops out of
regulation and delivers *less* current than commanded -- silently, in most hardware.
Every safety margin computed elsewhere in this package then describes a protocol that
was never actually delivered.

The voltage budget modelled here is

.. math::

    V_{required} = I\\,(R_{access} + R_{lead}) + \\Delta V_{polarisation}

- ``R_access`` is the ohmic spreading resistance into tissue, from the electrode
  geometry (Newman 1966 for a disc; exact forms for sphere and hemisphere).
- ``R_lead`` is the series resistance of the lead wire and connectors, which is
  measurable and often non-negligible for long thin microwires.
- ``Delta V_polarisation`` is the interfacial excursion from the water-window module,
  computed under the same conservative pure-capacitance assumption.

If you have measured the electrode impedance directly, pass it as
``measured_impedance_ohm``: that supersedes the geometric estimate, and the result
records which path was taken. An impedance measured at 1 kHz is the usual laboratory
number, and it is not the same quantity as the DC access resistance -- it already
folds in some interfacial capacitance -- so the two are reported separately rather
than blended.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..data import gabriel1996
from ..geometry.base import Electrode
from ..materials import Material, get_material
from ..protocol import StimProtocol
from .charge import charge_density_uC_cm2
from .water_window import effective_capacitance_uF_cm2, polarisation_V


@dataclass(frozen=True)
class ComplianceResult:
    """Voltage budget for one pulse."""

    current_uA: float
    access_resistance_ohm: float
    lead_resistance_ohm: float
    total_resistance_ohm: float
    ohmic_drop_V: float
    polarisation_V: float
    required_V: float
    available_V: float | None
    resistance_source: str
    access_resistance_is_exact: bool
    conductivity_note: str = ""

    @property
    def evaluated(self) -> bool:
        """Whether a stimulator compliance voltage was supplied to compare against."""
        return self.available_V is not None

    @property
    def passes(self) -> bool:
        """Whether the stimulator can supply the required voltage.

        ``True`` when no compliance voltage was supplied -- the check did not run.
        """
        if self.available_V is None:
            return True
        return self.required_V <= self.available_V

    @property
    def headroom_V(self) -> float:
        """Volts of spare compliance; negative means the source will drop out."""
        if self.available_V is None:
            return math.inf
        return self.available_V - self.required_V

    @property
    def utilisation(self) -> float:
        """Required voltage as a fraction of available compliance."""
        if self.available_V is None or self.available_V <= 0:
            return math.inf
        return self.required_V / self.available_V

    @property
    def max_current_uA(self) -> float:
        """Largest current the stimulator can actually drive into this load.

        Solves ``V = I*R + (I*W/A)/C_dl`` for ``I``; because both terms are linear in
        current, this reduces to scaling the requested current by the voltage ratio.
        """
        if self.available_V is None or self.required_V <= 0:
            return math.inf
        return self.current_uA * (self.available_V / self.required_V)

    def describe(self) -> str:
        """Multi-line summary."""
        exact = "exact" if self.access_resistance_is_exact else "equal-area approx."
        lines = [
            f"Compliance voltage ({self.resistance_source})",
            f"  access R      {self.access_resistance_ohm:.0f} ohm ({exact})",
        ]
        if self.conductivity_note:
            lines.append(f"  {self.conductivity_note}")
        if self.lead_resistance_ohm:
            lines.append(f"  lead R        {self.lead_resistance_ohm:.0f} ohm")
        lines += [
            f"  ohmic drop    {self.ohmic_drop_V:.3f} V",
            f"  polarisation  {self.polarisation_V:.3f} V",
            f"  required      {self.required_V:.3f} V",
        ]
        if self.available_V is None:
            lines.append("  available     not specified -> check NOT EVALUATED")
        else:
            verdict = "PASS" if self.passes else "INSUFFICIENT"
            lines += [
                f"  available     {self.available_V:.3f} V -> {verdict}",
                f"  headroom      {self.headroom_V:+.3f} V "
                f"({self.utilisation * 100:.1f} % used)",
            ]
            if not self.passes:
                lines.append(
                    f"  the source will drop out of regulation above "
                    f"{self.max_current_uA:.4g} uA; delivered current will be lower "
                    f"than commanded"
                )
        return "\n".join(lines)


def evaluate(
    electrode: Electrode,
    protocol: StimProtocol,
    *,
    material: Material | str | None = None,
    tissue_conductivity_S_per_m: float = 0.35,
    lead_resistance_ohm: float = 0.0,
    compliance_V: float | None = None,
    measured_impedance_ohm: float | None = None,
    capacitance_uF_cm2: float | None = None,
) -> ComplianceResult:
    """Compute the voltage a stimulator must supply to deliver ``protocol``."""
    if lead_resistance_ohm < 0 or not math.isfinite(lead_resistance_ohm):
        raise ValueError(
            f"lead_resistance_ohm must be finite and >= 0, got {lead_resistance_ohm!r}"
        )

    if measured_impedance_ohm is not None:
        if not math.isfinite(measured_impedance_ohm) or measured_impedance_ohm <= 0:
            raise ValueError(
                f"measured_impedance_ohm must be finite and > 0, "
                f"got {measured_impedance_ohm!r}"
            )
        access_r = measured_impedance_ohm
        source = "measured electrode impedance"
        is_exact = True
        conductivity_note = ""
    else:
        access_r = electrode.access_resistance_ohm(tissue_conductivity_S_per_m)
        source = f"geometric estimate at sigma = {tissue_conductivity_S_per_m:g} S/m"
        is_exact = electrode.access_resistance_is_exact
        gabriel_sigma = gabriel1996.conductivity_for_pulse(protocol.pulse_width_us)
        fold = tissue_conductivity_S_per_m / gabriel_sigma
        if fold > 1.5:
            conductivity_note = (
                f"CAUTION: Gabriel et al. (1996) give {gabriel_sigma:.3f} S/m for grey "
                f"matter at the\n  effective frequency of a "
                f"{protocol.pulse_width_us:g} us pulse -- {fold:.1f}x below the "
                f"{tissue_conductivity_S_per_m:g} S/m used here.\n  Access resistance "
                f"scales as 1/sigma, so the required voltage could be {fold:.1f}x "
                f"higher."
            )
        else:
            conductivity_note = ""

    total_r = access_r + lead_resistance_ohm
    current_A = protocol.current_uA * 1e-6
    ohmic = current_A * total_r

    # The material is resolved so that an unknown name fails here rather than silently
    # producing a voltage budget for an electrode that does not exist. It does not enter
    # the polarisation term itself: under the pure-capacitance interface model that term
    # depends only on charge density and the double-layer capacitance the caller chose.
    mat_key = material if material is not None else electrode.material
    mat = mat_key if isinstance(mat_key, Material) else get_material(str(mat_key))
    density = charge_density_uC_cm2(protocol.charge_per_phase_uC, electrode.area_cm2)
    # Same interfacial capacitance the water-window check uses: the polarisation term in
    # the voltage budget and the excursion inside the window are the same quantity.
    if capacitance_uF_cm2 is None:
        capacitance_uF_cm2 = effective_capacitance_uF_cm2(
            mat, anodic_first=protocol.anodic_first
        )
    polar = polarisation_V(density, capacitance_uF_cm2)

    return ComplianceResult(
        current_uA=protocol.current_uA,
        access_resistance_ohm=access_r,
        lead_resistance_ohm=lead_resistance_ohm,
        total_resistance_ohm=total_r,
        ohmic_drop_V=ohmic,
        polarisation_V=polar,
        required_V=ohmic + polar,
        available_V=compliance_V,
        resistance_source=source,
        access_resistance_is_exact=is_exact,
        conductivity_note=conductivity_note,
    )
