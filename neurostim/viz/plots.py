"""Figures for electrode safety assessment.

Each function states the claim its figure defends. If a figure cannot defend a claim,
it should not be in a manuscript, and it is not in this module.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np

from ..data import mccreery1990 as mccreery
from ..geometry.base import Electrode
from ..materials import Material, get_material, list_materials
from ..models import field as field_mod
from ..models import strength_duration as sd_mod
from ..models import thermal as thermal_mod
from ..protocol import StimProtocol
from ..safety import SafetyCalculator
from ..safety import shannon as shannon_mod
from .style import (
    DOUBLE_COLUMN_MM,
    PALETTE,
    SINGLE_COLUMN_MM,
    STATUS_COLOURS,
    apply_style,
    panel_label,
    subplots,
)


def shannon_safe_operating_area(
    calc: SafetyCalculator | None = None,
    *,
    ax=None,
    k_values: Sequence[float] = (
        shannon_mod.K_SHANNON,
        shannon_mod.K_MODERATE,
        shannon_mod.K_DAMAGE_OBSERVED,
    ),
    charge_range_uC: tuple[float, float] = (1e-3, 1e2),
    annotate: bool = True,
    show_data: bool = True,
):
    """Shannon safe-operating-area plot: charge per phase against charge density.

    **Claim defended:** whether an operating point falls below the Shannon damage
    separatrix, and by how much, given that the separatrix is a band (k = 1.5 to 2.0)
    rather than a line.

    This is the canonical presentation of the criterion, matching Fig. 8 of Merrill
    et al. (2005): each ``k`` is a straight line of slope -1 on log-log axes, because
    ``log(Q/A) = k - log(Q)``. The region below a line is the region their reprocessed
    histology showed no damage.
    """
    apply_style()
    if ax is None:
        _, ax = subplots(width_mm=SINGLE_COLUMN_MM, height_mm=68.0)

    if show_data:
        # McCreery et al. (1990) Table I. The line is a fit to these points; drawing it
        # without them asks the reader to take the separatrix on trust.
        for group, marker, face, edge, label in (
            (mccreery.undamaged(), "o", "white", STATUS_COLOURS["PASS"], "no damage"),
            (mccreery.partial(), "o", PALETTE["caution"], PALETTE["caution"], "some damage"),
            (mccreery.damaged(), "s", STATUS_COLOURS["FAIL"], STATUS_COLOURS["FAIL"], "damage"),
        ):
            if not group:
                continue
            ax.loglog(
                [p.charge_per_phase_uC for p in group],
                [p.charge_density_uC_cm2 for p in group],
                marker=marker,
                linestyle="none",
                markersize=3.4,
                markerfacecolor=face,
                markeredgecolor=edge,
                markeredgewidth=0.7,
                label=label,
                zorder=3,
            )

    q = np.logspace(math.log10(charge_range_uC[0]), math.log10(charge_range_uC[1]), 200)
    greys = (PALETTE["ink"], PALETTE["grey"], PALETTE["mid_grey"])
    for k, colour in zip(k_values, greys, strict=False):
        density = 10.0**k / q
        damaging = k >= shannon_mod.K_DAMAGE_OBSERVED
        ax.loglog(
            q,
            density,
            color=STATUS_COLOURS["FAIL"] if damaging else colour,
            linewidth=1.0,
            linestyle="-" if k == shannon_mod.K_SHANNON else "--",
            label=f"k = {k:.2f}" + (" (damage seen)" if damaging else ""),
            zorder=2,
        )

    if calc is not None:
        assessment = calc.assess()
        status = assessment.shannon
        colour = STATUS_COLOURS["PASS" if status.passes else "FAIL"]
        ax.loglog(
            [status.charge_per_phase_uC],
            [status.charge_density_uC_cm2],
            marker="o",
            markersize=5,
            markerfacecolor=colour,
            markeredgecolor="white",
            markeredgewidth=0.7,
            linestyle="none",
            zorder=5,
            label="protocol",
        )
        if annotate:
            ax.annotate(
                f"k = {status.k_metric:.2f}",
                xy=(status.charge_per_phase_uC, status.charge_density_uC_cm2),
                xytext=(8, 8),
                textcoords="offset points",
                fontsize=6.5,
                color=colour,
                fontweight="bold",
            )

    ax.set_xlabel("Charge per phase, $Q$ (µC per phase)")
    ax.set_ylabel("Charge density, $Q/A$ (µC cm$^{-2}$ per phase)")
    ax.set_title("Shannon safe operating area", pad=4)
    ax.legend(loc="upper right", handlelength=1.6, fontsize=5.4, ncol=1)
    ax.text(
        0.03,
        0.04,
        "points: McCreery et al. 1990 Table I\n(400 us, 50 Hz, 7 h, cat cortex)",
        transform=ax.transAxes,
        fontsize=6,
        color=PALETTE["grey"],
        va="bottom",
    )
    return ax


def current_limit_sweep(
    electrode: Electrode,
    protocol: StimProtocol,
    currents_uA: Iterable[float] | None = None,
    *,
    ax=None,
    compliance_V: float | None = None,
    **calculator_kwargs,
):
    """Which mechanism binds the stimulation amplitude, across a current range.

    **Claim defended:** the maximum usable amplitude, and which physical limit sets it.
    Plotting the limits together rather than reporting them separately is the point:
    the binding constraint is often not the one people quote.
    """
    apply_style()
    if ax is None:
        _, ax = subplots(width_mm=SINGLE_COLUMN_MM, height_mm=62.0)

    if currents_uA is None:
        base = SafetyCalculator(
            electrode, protocol, compliance_V=compliance_V, **calculator_kwargs
        )
        top = max(base.max_current_shannon_uA, base.max_current_cic_uA) * 1.6
        currents_uA = np.logspace(
            math.log10(max(top * 1e-3, 1e-3)), math.log10(top), 120
        )
    currents = np.asarray(list(currents_uA), dtype=float)

    from dataclasses import replace

    shannon_limit = np.empty_like(currents)
    cic_limit = np.empty_like(currents)
    compliance_limit = np.full_like(currents, np.nan)
    for i, current in enumerate(currents):
        calc = SafetyCalculator(
            electrode,
            replace(protocol, current_uA=float(current)),
            compliance_V=compliance_V,
            **calculator_kwargs,
        )
        shannon_limit[i] = calc.max_current_shannon_uA
        cic_limit[i] = calc.max_current_cic_uA
        if compliance_V is not None:
            compliance_limit[i] = calc.assess().compliance.max_current_uA

    ax.loglog(currents, currents, color=PALETTE["light_grey"], linewidth=0.8,
              linestyle=":", label="requested", zorder=1)
    ax.loglog(currents, shannon_limit, color=PALETTE["signal"], label="Shannon limit")
    ax.loglog(currents, cic_limit, color=PALETTE["accent"], label="charge-injection limit")
    if compliance_V is not None:
        ax.loglog(
            currents,
            compliance_limit,
            color=PALETTE["grey"],
            linestyle="--",
            label="compliance limit",
        )

    binding = np.minimum(shannon_limit, cic_limit)
    if compliance_V is not None:
        binding = np.minimum(binding, compliance_limit)
    ax.fill_between(currents, binding, currents.min(), color=PALETTE["pass"], alpha=0.07,
                    linewidth=0, zorder=0)

    crossing = binding[0]
    ax.axhline(crossing, color=PALETTE["fail"], linewidth=0.7, linestyle="-", alpha=0.6)
    ax.annotate(
        f"binding limit {crossing:.3g} µA",
        xy=(currents[0], crossing),
        xytext=(2, 3),
        textcoords="offset points",
        fontsize=6,
        color=PALETTE["fail"],
    )

    ax.set_xlabel("Requested current (µA)")
    ax.set_ylabel("Permitted current (µA)")
    ax.set_title(f"Amplitude limits, {electrode.material}", pad=4)
    ax.legend(loc="lower right", handlelength=1.6)
    return ax


def strength_duration(
    rheobase_uA: float,
    chronaxie_us: float,
    *,
    axes=None,
    pulse_widths_us: np.ndarray | None = None,
):
    """Threshold current and threshold charge against pulse width.

    **Claim defended:** shortening the pulse raises the threshold current but *lowers*
    the injected charge, so efficacy and charge-based safety limits favour the same
    direction. This is the practical reason short pulses dominate modern protocols.
    """
    apply_style()
    if axes is None:
        _, axes = subplots(
            1, 2, width_mm=DOUBLE_COLUMN_MM * 0.62, height_mm=52.0
        )
    ax_i, ax_q = axes

    w = (
        np.logspace(1, 3.4, 200)
        if pulse_widths_us is None
        else np.asarray(pulse_widths_us, dtype=float)
    )
    i_th = np.asarray(sd_mod.weiss_threshold_uA(w, rheobase_uA, chronaxie_us))
    q_th = np.asarray(sd_mod.weiss_threshold_charge_uC(w, rheobase_uA, chronaxie_us))

    ax_i.semilogx(w, i_th, color=PALETTE["signal"])
    ax_i.axhline(rheobase_uA, color=PALETTE["grey"], linewidth=0.7, linestyle="--")
    ax_i.axvline(chronaxie_us, color=PALETTE["mid_grey"], linewidth=0.7, linestyle=":")
    ax_i.annotate(
        "rheobase",
        xy=(w[0], rheobase_uA),
        xytext=(2, 3),
        textcoords="offset points",
        fontsize=6,
        color=PALETTE["grey"],
    )
    ax_i.annotate(
        f"chronaxie\n{chronaxie_us:g} µs",
        xy=(chronaxie_us, 2 * rheobase_uA),
        xytext=(4, 2),
        textcoords="offset points",
        fontsize=6,
        color=PALETTE["mid_grey"],
    )
    ax_i.set_xlabel("Pulse width (µs)")
    ax_i.set_ylabel("Threshold current (µA)")
    ax_i.set_title("Strength–duration", pad=4)
    panel_label(ax_i, "a")

    ax_q.semilogx(w, q_th, color=PALETTE["accent"])
    ax_q.set_xlabel("Pulse width (µs)")
    ax_q.set_ylabel("Threshold charge (µC)")
    ax_q.set_title("Charge–duration", pad=4)
    panel_label(ax_q, "b")

    return axes


def radial_field_profile(
    current_uA: float,
    electrode: Electrode | None = None,
    *,
    ax=None,
    sigma_S_per_m: float = field_mod.BRAIN_CONDUCTIVITY_S_PER_M,
    max_distance_um: float = 5000.0,
):
    """Extracellular potential and field magnitude against radial distance.

    **Claim defended:** the spatial scale over which the stimulus is electrically
    significant, under an explicitly homogeneous-isotropic point-source assumption.
    """
    apply_style()
    if ax is None:
        _, ax = subplots(width_mm=SINGLE_COLUMN_MM, height_mm=58.0)

    r_min = electrode.equivalent_radius_um if electrode is not None else 10.0
    profile = field_mod.radial_profile(
        current_uA, r_min, max_distance_um, 250, sigma_S_per_m, electrode=electrode
    )

    potential_mV = profile.potential_V * 1e3
    ax.loglog(profile.distance_um, potential_mV, color=PALETTE["signal"])
    ax.set_xlabel("Distance from electrode (µm)")
    ax.set_ylabel("Potential (mV)", color=PALETTE["signal"])
    ax.tick_params(axis="y", colors=PALETTE["signal"])

    ax2 = ax.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_linewidth(0.8)
    ax2.loglog(
        profile.distance_um,
        profile.field_V_per_m,
        color=PALETTE["accent"],
        linestyle="--",
    )
    ax2.set_ylabel("Field (V m$^{-1}$)", color=PALETTE["accent"])
    ax2.tick_params(axis="y", colors=PALETTE["accent"])

    # Potential falls as 1/r and field as 1/r^2, but independent autoscaling on twin
    # axes can place the two curves on top of one another, making them read as a single
    # line and hiding exactly the difference in slope the panel exists to show. Push the
    # field axis down by a decade so the curves stay visually separate, and label each
    # curve directly rather than relying on axis colour alone.
    ax.set_ylim(potential_mV.min() / 1.5, potential_mV.max() * 1.5)
    field = profile.field_V_per_m
    ax2.set_ylim(field.min() / 25.0, field.max() * 1.5)

    n = len(profile.distance_um)
    v_at, e_at = int(n * 0.62), int(n * 0.22)
    ax.annotate(
        r"$V \propto 1/r$",
        xy=(profile.distance_um[v_at], potential_mV[v_at]),
        xytext=(3, -12),
        textcoords="offset points",
        fontsize=6,
        color=PALETTE["signal"],
        fontweight="bold",
    )
    ax2.annotate(
        r"$E \propto 1/r^{2}$",
        xy=(profile.distance_um[e_at], field[e_at]),
        xytext=(3, 5),
        textcoords="offset points",
        fontsize=6,
        color=PALETTE["accent"],
        fontweight="bold",
    )

    ax.set_title(f"Point-source field, {current_uA:g} µA", pad=4)
    ax.text(
        0.03,
        0.05,
        "homogeneous isotropic medium;\nno anisotropy or encapsulation",
        transform=ax.transAxes,
        fontsize=5.8,
        color=PALETTE["grey"],
        va="bottom",
    )
    return ax


def thermal_profile(
    power_W: float,
    source_radius_um: float,
    *,
    axes=None,
    tissue: thermal_mod.TissueThermalProperties = thermal_mod.BRAIN,
    max_distance_um: float = 10000.0,
    times_s: np.ndarray | None = None,
):
    """Steady-state spatial decay and the approach to steady state.

    **Claim defended:** the magnitude and spatial reach of ohmic tissue heating, and
    the timescale over which it saturates.
    """
    apply_style()
    if axes is None:
        _, axes = subplots(1, 2, width_mm=DOUBLE_COLUMN_MM * 0.62, height_mm=52.0)
    ax_r, ax_t = axes

    r = np.linspace(source_radius_um, max_distance_um, 300)
    rise = np.asarray(thermal_mod.pennes_steady_state_sphere(power_W, source_radius_um, r, tissue))
    ax_r.plot(r * 1e-3, rise * 1e3, color=PALETTE["fail"])
    depth = tissue.thermal_penetration_depth_m
    if math.isfinite(depth):
        ax_r.axvline(depth * 1e3, color=PALETTE["mid_grey"], linewidth=0.7, linestyle=":")
        ax_r.annotate(
            f"L = {depth * 1e3:.1f} mm",
            xy=(depth * 1e3, rise.max() * 1e3 * 0.6),
            xytext=(3, 0),
            textcoords="offset points",
            fontsize=6,
            color=PALETTE["mid_grey"],
        )
    ax_r.set_xlabel("Distance from source (mm)")
    ax_r.set_ylabel("Temperature rise (mK)")
    ax_r.set_title("Steady state", pad=4)
    panel_label(ax_r, "a")

    t = np.logspace(-1, 3.5, 40) if times_s is None else np.asarray(times_s, dtype=float)
    transient = thermal_mod.pennes_transient_sphere(power_W, source_radius_um, t, tissue)
    steady = thermal_mod.peak_temperature_rise_K(power_W, source_radius_um, tissue)
    ax_t.semilogx(t, transient * 1e3, color=PALETTE["fail"])
    ax_t.axhline(steady * 1e3, color=PALETTE["grey"], linewidth=0.7, linestyle="--")
    ax_t.annotate(
        "steady state",
        xy=(t[0], steady * 1e3),
        xytext=(2, 2),
        textcoords="offset points",
        fontsize=6,
        color=PALETTE["grey"],
    )
    ax_t.set_xlabel("Time (s)")
    ax_t.set_ylabel("Surface rise (mK)")
    ax_t.set_title("Approach to steady state", pad=4)
    panel_label(ax_t, "b")

    return axes


def material_comparison(
    electrode: Electrode,
    protocol: StimProtocol,
    *,
    ax=None,
    materials: Sequence[Material | str] | None = None,
    policy: str = "conservative",
):
    """Applied charge density against each material's charge-injection limit.

    **Claim defended:** which electrode materials can carry the intended protocol on
    this geometry. Limits span nearly three orders of magnitude, so the axis is
    logarithmic and the applied value is drawn as a single reference line.
    """
    apply_style()
    if ax is None:
        _, ax = subplots(width_mm=SINGLE_COLUMN_MM, height_mm=62.0)

    mats = [
        m if isinstance(m, Material) else get_material(m)
        for m in (materials if materials is not None else list_materials())
    ]
    applied = protocol.charge_per_phase_uC / electrode.area_cm2
    limits = [m.cic_uC_cm2(policy) for m in mats]  # type: ignore[arg-type]
    colours = [
        STATUS_COLOURS["PASS"] if limit >= applied else STATUS_COLOURS["FAIL"]
        for limit in limits
    ]

    y = np.arange(len(mats))
    ax.barh(y, limits, color=colours, height=0.62, linewidth=0)
    ax.axvline(applied, color=PALETTE["ink"], linewidth=1.0)
    ax.annotate(
        f"applied {applied:.3g} µC cm$^{{-2}}$",
        xy=(applied, len(mats) - 0.4),
        xytext=(4, 0),
        textcoords="offset points",
        fontsize=6,
        fontweight="bold",
        color=PALETTE["ink"],
    )
    for i, m in enumerate(mats):
        if not m.cic.verified:
            ax.annotate(
                "provisional",
                xy=(limits[i], i),
                xytext=(3, 0),
                textcoords="offset points",
                fontsize=5.5,
                color=PALETTE["caution"],
                va="center",
            )

    ax.set_xscale("log")
    ax.set_yticks(y)
    ax.set_yticklabels([m.key for m in mats])
    ax.set_xlabel("Charge-injection limit (µC cm$^{-2}$)")
    ax.set_title(f"Material limits, {policy} policy", pad=4)
    ax.invert_yaxis()
    return ax


def safety_summary(
    calc: SafetyCalculator,
    *,
    width_mm: float = DOUBLE_COLUMN_MM,
    compliance_V: float | None = None,
):
    """Four-panel summary figure: the hero Shannon panel plus supporting evidence.

    **Claim defended:** the complete safety position of one electrode/protocol pair --
    where it sits against the tissue criterion, what binds its amplitude, how it
    compares across materials, and how far its field reaches.
    """
    apply_style()
    fig, axes = subplots(2, 2, width_mm=width_mm, height_mm=115.0)
    (ax_a, ax_b), (ax_c, ax_d) = axes

    shannon_safe_operating_area(calc, ax=ax_a)
    panel_label(ax_a, "a")

    current_limit_sweep(
        calc.e, calc.p, ax=ax_b, compliance_V=compliance_V or calc.compliance_V
    )
    panel_label(ax_b, "b")

    material_comparison(calc.e, calc.p, ax=ax_c, policy=calc.policy)
    panel_label(ax_c, "c")

    radial_field_profile(calc.p.current_uA, calc.e, ax=ax_d)
    panel_label(ax_d, "d")

    assessment = calc.assess()
    fig.suptitle(
        f"{calc.e.shape_name} electrode, {calc.material.key} — {assessment.status.value}",
        fontsize=8.5,
        fontweight="bold",
        y=1.0,
    )
    fig.tight_layout(pad=1.1, h_pad=2.2, w_pad=2.6)
    return fig, axes
