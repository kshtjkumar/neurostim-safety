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
  geometry (Newman 1966 for a disc; exact forms for sphere and hemisphere; the equal-area
  sphere for immersed bodies such as the DBS band, +0.6 % above a converged solve at the
  clinical aspect and high at every aspect -- see ``Electrode.access_resistance_ohm``).
- ``R_lead`` is the series resistance of the lead wire and connectors, which is
  measurable and often non-negligible for long thin microwires.
- ``Delta V_polarisation`` is the interfacial excursion from the water-window module,
  computed under the same conservative pure-capacitance assumption.

**The return path** (ledger 5, fix plan D7). Current leaves through a counter electrode,
and a two-terminal pair has two interfaces and two spreading resistances. Supply
``counter_electrode`` and ``counter_separation_um`` and the budget becomes

.. math::

    V = I\\,(R_a + R_c - 2/(G \\sigma d) + R_{lead}) + \\Delta V_a + \\Delta V_c

**Each phase at its own polarity** (ledger 131). ``C_eff`` is polarity-specific -- Pt is
250 uF/cm^2 cathodic and 125 anodic -- so the return phase polarises the active electrode
at the opposite polarity's value and the counter at the leading polarity's. For a
cathodic-first Pt pulse the anodic return phase therefore polarises twice as much as the
leading phase and is the one that binds. A measured ``capacitance_uF_cm2`` is one value and
applies to both phases.

with each electrode's own access resistance, ``G = 4 pi`` in a full space or ``2 pi`` for
two electrodes flush on one insulating plane (the convention of
:attr:`~neurostim.geometry.base.Electrode.environment`), and each interface's own
polarisation. The counter's capacitance is derived from its own material at the opposite
phase polarity. The mutual term is first-order superposition of two compact sources, so
two identical immersed contacts are *not* twice one: two 3389 contacts at 2 mm give
431.6 ohm against a naive 658.9. At large separation it vanishes, and the requirement
exactly doubles.

Without a counter electrode the arithmetic is the single-interface budget above,
unchanged. The check says so and is at best CAUTION, because under-estimating the
required voltage is the anti-conservative direction. The equilibrium-potential difference
between two dissimilar electrode materials is **not** modelled.

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
from ..units import charge_uC
from ._limits import floor_to_pass, format_limit
from .charge import charge_density_uC_cm2
from .water_window import effective_capacitance_uF_cm2, polarisation_V


def required_voltage_V(
    current_uA: float,
    *,
    total_resistance_ohm: float,
    pulse_width_us: float,
    area_cm2: float,
    capacitance_uF_cm2: float,
    counter_area_cm2: float = 0.0,
    counter_capacitance_uF_cm2: float = 0.0,
) -> float:
    """Voltage the stimulator must supply to deliver ``current_uA`` into this load.

    ``counter_area_cm2 = 0`` means no counter interface is modelled; otherwise the same
    charge polarises the counter over its own area (ledger 5).

    One expression, used both to report the requirement and to back-solve the limit. The
    back-solve used to scale the requested current by the voltage ratio, which is exact in
    real arithmetic and not in floating point: of 36 measured (electrode, compliance,
    pulse width) combinations, 6 reported limits FAILed their own compliance check and 14
    more sat below the boundary. Sharing the expression is what makes
    :attr:`ComplianceResult.max_current_uA` an inverse of :attr:`ComplianceResult.passes`
    rather than an approximation of one.
    """
    ohmic = (current_uA * 1e-6) * total_resistance_ohm
    charge = charge_uC(current_uA, pulse_width_us)
    density = charge_density_uC_cm2(charge, area_cm2)
    required = ohmic + polarisation_V(density, capacitance_uF_cm2)
    if counter_area_cm2 > 0.0:
        counter_density = charge_density_uC_cm2(charge, counter_area_cm2)
        required += polarisation_V(counter_density, counter_capacitance_uF_cm2)
    return required


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
    pulse_width_us: float
    area_cm2: float
    capacitance_uF_cm2: float
    conductivity_note: str = ""
    return_phase_current_uA: float = 0.0
    return_phase_width_us: float = 0.0
    return_current_factor: float = 0.0
    """Return-phase amplitude as a multiple of the leading one; 0.0 when there is none.

    Stored rather than derived from the two amplitudes, because the back-solve needs the
    return phase at amplitudes the protocol was never configured at, and a division of one
    stored amplitude by another is not the expression the protocol used to make them.
    """
    return_required_V: float = 0.0
    """Voltage the return phase alone demands, at the configured amplitude."""
    counter_access_resistance_ohm: float = 0.0
    """The counter electrode's own spreading resistance; 0.0 when none is modelled."""
    mutual_resistance_ohm: float = 0.0
    """``2/(G sigma d)``, subtracted from the two access resistances."""
    counter_area_cm2: float = 0.0
    """The counter's geometric area; 0.0 means the monopolar budget (no counter)."""
    counter_capacitance_uF_cm2: float = 0.0
    counter_polarisation_V: float = 0.0
    """The counter interface's excursion at the configured amplitude, leading phase."""
    return_capacitance_uF_cm2: float = 0.0
    """The active interface's C_eff during the return phase, at the opposite polarity.

    0.0 means "the same as :attr:`capacitance_uF_cm2`", which is also what a measured
    ``capacitance_uF_cm2`` gives: one measurement, not split by polarity.
    """
    counter_return_capacitance_uF_cm2: float = 0.0
    """The counter's C_eff during the return phase, when it carries the leading polarity."""

    @property
    def counter_modelled(self) -> bool:
        """Whether the budget includes a counter electrode, or assumes one interface."""
        return self.counter_area_cm2 > 0.0

    @property
    def has_return_phase(self) -> bool:
        """Whether a second phase draws current through the same load.

        False for a monophasic pulse and for a biphasic one recovering no charge.
        """
        return self.return_current_factor > 0.0 and self.return_phase_width_us > 0.0

    def required_V_at(self, current_uA: float) -> float:
        """Voltage the stimulator must supply for the worse of the two phases.

        The quantity :attr:`max_current_uA` inverts, and the one :attr:`required_V` is at
        the configured amplitude. Both phases are linear in the leading amplitude, so the
        maximum of the two is too -- which is what keeps the closed-form seed exact.

        The return phase used to be invisible here (ledger 4): with
        ``return_phase_ratio = 0.2`` a 1000 uA protocol drives 5000 uA through the same
        access resistance and the check reported the leading phase's 0.524 V, when the
        return phase alone needs 2.59 V. A stimulator sized on that number drops out of
        regulation during the return phase, silently.
        """
        leading = required_voltage_V(
            current_uA,
            total_resistance_ohm=self.total_resistance_ohm,
            pulse_width_us=self.pulse_width_us,
            area_cm2=self.area_cm2,
            capacitance_uF_cm2=self.capacitance_uF_cm2,
            counter_area_cm2=self.counter_area_cm2,
            counter_capacitance_uF_cm2=self.counter_capacitance_uF_cm2,
        )
        if not self.has_return_phase:
            return leading
        # Each phase at its own polarity, on both electrodes (ledger 131): during the return
        # phase the active electrode carries the opposite polarity and the counter the
        # leading one, and C_eff is polarity-specific.
        returning = required_voltage_V(
            current_uA * self.return_current_factor,
            total_resistance_ohm=self.total_resistance_ohm,
            pulse_width_us=self.return_phase_width_us,
            area_cm2=self.area_cm2,
            capacitance_uF_cm2=self.return_capacitance_uF_cm2 or self.capacitance_uF_cm2,
            counter_area_cm2=self.counter_area_cm2,
            counter_capacitance_uF_cm2=(
                self.counter_return_capacitance_uF_cm2 or self.counter_capacitance_uF_cm2
            ),
        )
        return max(leading, returning)

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
        current, that reduces to scaling the requested current by the voltage ratio -- and
        then the answer is settled onto the boundary of the *forward* comparison, which
        recomputes the voltage rather than scaling it. The two differ by up to an ulp and
        the difference is a reported maximum that fails its own check (ledger 9).
        """
        if self.available_V is None or self.required_V <= 0:
            return math.inf
        available_V = self.available_V
        return floor_to_pass(
            self.current_uA * (available_V / self.required_V),
            lambda current_uA: self.required_V_at(current_uA) <= available_V,
            name="Compliance voltage",
        )

    def describe(self) -> str:
        """Multi-line summary."""
        exact = "exact" if self.access_resistance_is_exact else "equal-area approx."
        lines = [
            f"Compliance voltage ({self.resistance_source})",
            f"  access R      {self.access_resistance_ohm:.0f} ohm ({exact})",
        ]
        if self.conductivity_note:
            lines.append(f"  {self.conductivity_note}")
        if self.counter_modelled:
            lines += [
                f"  counter R     {self.counter_access_resistance_ohm:.0f} ohm",
                f"  mutual        -{self.mutual_resistance_ohm:.0f} ohm (the two "
                f"electrodes share the medium)",
            ]
        else:
            lines.append(
                "  monopolar single-interface budget assumed; supply counter_electrode "
                "for a two-terminal estimate"
            )
        if self.lead_resistance_ohm:
            lines.append(f"  lead R        {self.lead_resistance_ohm:.0f} ohm")
        lines += [
            f"  ohmic drop    {self.ohmic_drop_V:.3f} V",
            f"  polarisation  {self.polarisation_V:.3f} V",
        ]
        if self.counter_modelled:
            lines.append(f"  counter pol.  {self.counter_polarisation_V:.3f} V")
        if self.has_return_phase:
            lines.append(
                f"  return phase  {self.return_required_V:.3f} V "
                f"({self.return_phase_current_uA:g} uA x "
                f"{self.return_phase_width_us:g} us)"
            )
        lines.append(f"  required      {self.required_V:.3f} V")
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
                    f"{format_limit(self.max_current_uA)} uA; delivered current will "
                    f"be lower "
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
    counter_electrode: Electrode | None = None,
    counter_separation_um: float | None = None,
) -> ComplianceResult:
    """Compute the voltage a stimulator must supply to deliver ``protocol``.

    ``counter_electrode`` and ``counter_separation_um`` go together. See
    :func:`validate_counter` for what is refused and why.
    """
    validate_counter(
        electrode, counter_electrode, counter_separation_um, measured_impedance_ohm
    )
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

    counter_r = 0.0
    mutual_r = 0.0
    counter_area = 0.0
    counter_capacitance = 0.0
    counter_return_capacitance = 0.0
    if counter_electrode is not None and counter_separation_um is not None:
        counter_r = counter_electrode.access_resistance_ohm(tissue_conductivity_S_per_m)
        factor = 2.0 * math.pi if electrode.environment == "half_space" else 4.0 * math.pi
        mutual_r = 2.0 / (factor * tissue_conductivity_S_per_m * counter_separation_um * 1e-6)
        counter_area = counter_electrode.area_cm2
        # The counter carries the opposite phase, so it sees the other polarity -- in the
        # leading phase the opposite of the protocol's, in the return phase the same.
        counter_mat = get_material(counter_electrode.material)
        counter_capacitance = effective_capacitance_uF_cm2(
            counter_mat, anodic_first=not protocol.anodic_first
        )
        counter_return_capacitance = effective_capacitance_uF_cm2(
            counter_mat, anodic_first=protocol.anodic_first
        )

    total_r = access_r + counter_r - mutual_r + lead_resistance_ohm
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
        # The return phase is the other polarity, whose C_eff differs for most materials
        # (Pt 250 cathodic against 125 anodic). A measured capacitance is one value and is
        # used for both phases.
        return_capacitance = effective_capacitance_uF_cm2(
            mat, anodic_first=not protocol.anodic_first
        )
    else:
        return_capacitance = capacitance_uF_cm2
    polar = polarisation_V(density, capacitance_uF_cm2)

    # The return phase's own budget. Its amplitude is a fixed multiple of the leading
    # one, taken from the protocol rather than divided out of two amplitudes, so the
    # back-solve can ask what the return phase does at an amplitude the protocol was
    # never configured at.
    return_factor = protocol.return_phase_current_at_uA(1.0)
    leading_required = required_voltage_V(
        protocol.current_uA,
        total_resistance_ohm=total_r,
        pulse_width_us=protocol.pulse_width_us,
        area_cm2=electrode.area_cm2,
        capacitance_uF_cm2=capacitance_uF_cm2,
        counter_area_cm2=counter_area,
        counter_capacitance_uF_cm2=counter_capacitance,
    )
    return_required = 0.0
    if return_factor > 0.0 and protocol.return_phase_width_us > 0.0:
        return_required = required_voltage_V(
            protocol.return_phase_current_uA,
            total_resistance_ohm=total_r,
            pulse_width_us=protocol.return_phase_width_us,
            area_cm2=electrode.area_cm2,
            capacitance_uF_cm2=return_capacitance,
            counter_area_cm2=counter_area,
            counter_capacitance_uF_cm2=counter_return_capacitance,
        )
    counter_polar = (
        polarisation_V(
            charge_density_uC_cm2(protocol.charge_per_phase_uC, counter_area),
            counter_capacitance,
        )
        if counter_area > 0.0
        else 0.0
    )

    return ComplianceResult(
        current_uA=protocol.current_uA,
        access_resistance_ohm=access_r,
        lead_resistance_ohm=lead_resistance_ohm,
        total_resistance_ohm=total_r,
        ohmic_drop_V=ohmic,
        polarisation_V=polar,
        required_V=max(leading_required, return_required),
        available_V=compliance_V,
        resistance_source=source,
        access_resistance_is_exact=is_exact,
        pulse_width_us=protocol.pulse_width_us,
        area_cm2=electrode.area_cm2,
        capacitance_uF_cm2=capacitance_uF_cm2,
        conductivity_note=conductivity_note,
        return_phase_current_uA=protocol.return_phase_current_uA,
        return_phase_width_us=protocol.return_phase_width_us,
        return_current_factor=return_factor,
        return_required_V=return_required,
        counter_access_resistance_ohm=counter_r,
        mutual_resistance_ohm=mutual_r,
        counter_area_cm2=counter_area,
        counter_capacitance_uF_cm2=counter_capacitance,
        counter_polarisation_V=counter_polar,
        return_capacitance_uF_cm2=return_capacitance,
        counter_return_capacitance_uF_cm2=counter_return_capacitance,
    )


def validate_counter(
    electrode: Electrode,
    counter_electrode: Electrode | None,
    counter_separation_um: float | None,
    measured_impedance_ohm: float | None = None,
) -> None:
    """Refuse a counter-electrode setting the two-terminal budget cannot honestly model.

    * a counter without a separation, or a separation without a counter: half an input;
    * a separation that is not finite, or not larger than the two equal-area radii: the
      superposition that gives the mutual term needs two separate bodies;
    * a half-space electrode with a full-space counter, or the reverse: no single
      superposition applies to one source flush in a plane and one immersed;
    * a counter with ``measured_impedance_ohm``: a measured impedance may already include
      the return path, and adding the counter's own resistance would count it twice.
    """
    if counter_electrode is None and counter_separation_um is None:
        return
    if counter_electrode is None:
        raise ValueError(
            "counter_separation_um was given without a counter_electrode"
        )
    if counter_separation_um is None:
        raise ValueError(
            "counter_electrode requires counter_separation_um (centre to centre, um)"
        )
    if not math.isfinite(counter_separation_um):
        raise ValueError(
            f"counter_separation_um must be finite, got {counter_separation_um!r}"
        )
    if counter_electrode.environment != electrode.environment:
        raise ValueError(
            f"counter_electrode is {counter_electrode.environment} and electrode is "
            f"{electrode.environment}: the mutual resistance of one source flush in a plane "
            f"and one immersed has no single superposition, so the two-terminal budget "
            f"cannot be computed"
        )
    if measured_impedance_ohm is not None:
        raise ValueError(
            f"measured_impedance_ohm ({measured_impedance_ohm!r} ohm) and counter_electrode "
            f"together are ambiguous: the measurement may already include the counter's "
            f"return path, and adding the counter's resistance would count it twice. "
            f"Supply one or the other"
        )
    closest = _reach_um(electrode) + _reach_um(counter_electrode)
    if counter_separation_um <= closest:
        raise ValueError(
            f"counter_separation_um ({counter_separation_um!r} um) must exceed the sum of "
            f"the electrode's and counter_electrode's half-extents ({closest:.4g} um): at "
            f"that distance the two overlap, and the superposition that gives the mutual "
            f"term needs two separate bodies"
        )


def _reach_um(electrode: Electrode) -> float:
    """How far an electrode extends from its centre, for the overlap guard.

    The larger of the equal-area substitute's radius and half the largest defining
    dimension. The substitute alone is too small for an elongated body: a 3389 band's
    equal-area sphere is 690 um across the middle, but the band is 1500 um long, so two on
    one shaft overlap below a 1500 um centre spacing (ledger 130).
    """
    substitute = (
        electrode.equivalent_sphere_radius_um
        if electrode.environment == "full_space"
        else electrode.equivalent_radius_um
    )
    dimensions = electrode.dimensions().values()
    return max(substitute, max(dimensions, default=0.0) / 2.0)
