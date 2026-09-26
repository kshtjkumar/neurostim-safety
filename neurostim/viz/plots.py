"""Figures for electrode safety assessment.

Each function states the claim its figure defends. If a figure cannot defend a claim,
it should not be in a manuscript, and it is not in this module.
"""

from __future__ import annotations

import inspect
import math
import textwrap
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

from ..data import mccreery1990 as mccreery
from ..geometry.base import Electrode
from ..materials import Material, get_material, list_materials
from ..models import field as field_mod
from ..models import strength_duration as sd_mod
from ..models import thermal as thermal_mod
from ..protocol import StimProtocol
from ..safety import LIMIT_BEARING, SafetyCalculator
from ..safety import shannon as shannon_mod
from ..safety._limits import format_limit
from .style import (
    CATEGORICAL,
    DOUBLE_COLUMN_MM,
    PALETTE,
    SINGLE_COLUMN_MM,
    STATUS_COLOURS,
    apply_style,
    panel_label,
    subplots,
)

_NOT_A_SETTING = frozenset({"self", "electrode", "protocol"})
"""Constructor parameters of :class:`SafetyCalculator` that are not settings."""


def _calculator_settings(calc: SafetyCalculator) -> dict[str, Any]:
    """Every construction setting of ``calc``, ready to rebuild it elsewhere.

    Read off the constructor signature rather than listed here, because a listed set is a
    set that goes stale, and ledger 48 is what a stale one costs: ``safety_summary``
    forwarded the electrode and the protocol and stopped, so panel (b) recomputed all
    three of its curves at the library defaults (k = 1.5, conservative, sigma = 0.35)
    while the suptitle carried the user's verdict. At ``k = 1.2, sigma = 0.10`` the panel
    annotated a binding limit of 6878 uA against the assessment's 4869.59, with the drawn
    Shannon limit 1.41x and the drawn compliance limit 3.44x the true ones -- both in the
    permissive direction, on the figure the README tells users to put in a manuscript.

    Every setting is stored on the calculator under its own parameter name, so a new one
    is forwarded the day it is added. One that is not raises rather than being dropped: a
    silently missing setting is exactly the defect this exists to close.
    """
    settings: dict[str, Any] = {}
    for name in inspect.signature(SafetyCalculator.__init__).parameters:
        if name in _NOT_A_SETTING:
            continue
        try:
            settings[name] = getattr(calc, name)
        except AttributeError:  # pragma: no cover - a new setting stored under a new name
            raise AttributeError(
                f"SafetyCalculator takes {name!r} at construction but does not store it "
                f"under that name, so figures cannot forward it. Store it as "
                f"self.{name}, or this panel will silently draw a library default "
                f"beside the user's verdict (ledger 48)."
            ) from None
    return settings


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

    With a calculator, its own ``k`` is drawn solid and labelled "this assessment", added
    to the reference values when it is not one of them: it is the line the operating
    point's colour was decided against (ledger 55).
    """
    apply_style()
    if ax is None:
        _, ax = subplots(width_mm=SINGLE_COLUMN_MM, height_mm=68.0)

    if show_data:
        # McCreery et al. (1990) Table I. The line is a fit to these points; drawing it
        # without them asks the reader to take the separatrix on trust. Each group has its
        # own shape as well as its own colour (ledger 56): the two greens and reds read
        # alike in greyscale and to a deuteranopic reader.
        for group, marker, face, edge, label in (
            (mccreery.undamaged(), "o", "white", STATUS_COLOURS["PASS"], "no damage"),
            (mccreery.partial(), "^", PALETTE["caution"], PALETTE["caution"], "some damage"),
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
    # The separatrix that decided the verdict is the assessment's own k, and it is drawn,
    # solid and named, whether or not it is one of the reference values (ledger 55). The
    # panel drew only the module constants, so at calc.k = 2.0 a point above the solid
    # k = 1.5 line was coloured as passing, and the line it passed against was not there.
    decided = calc.k if calc is not None else None
    solid = decided if decided is not None else shannon_mod.K_SHANNON
    lines = [(k, colour) for k, colour in zip(k_values, greys, strict=False)]
    if decided is not None and not any(math.isclose(k, decided) for k, _ in lines):
        lines.append((decided, PALETTE["ink"]))
    for k, colour in lines:
        density = 10.0**k / q
        damaging = k >= shannon_mod.K_DAMAGE_OBSERVED
        notes = [
            note
            for note, applies in (
                ("damage seen", damaging),
                ("this assessment", decided is not None and math.isclose(k, decided)),
            )
            if applies
        ]
        ax.loglog(
            q,
            density,
            color=STATUS_COLOURS["FAIL"] if damaging else colour,
            linewidth=1.0,
            linestyle="-" if math.isclose(k, solid) else "--",
            label=f"k = {k:.2f}" + (f" ({', '.join(notes)})" if notes else ""),
            zorder=2,
        )

    if calc is not None:
        assessment = calc.assess()
        status = assessment.shannon
        colour = STATUS_COLOURS["PASS" if status.passes else "FAIL"]
        ax.loglog(
            [status.charge_per_phase_uC],
            [status.charge_density_uC_cm2],
            # Shape as well as colour (ledger 56).
            marker="o" if status.passes else "X",
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

    Both the candidate set and the binding amplitude are read off
    :meth:`SafetyCalculator.assess`. This panel used to compute its own
    ``min(shannon, cic, compliance)`` from the 0.1.0-compat properties -- the three-check
    minimum C1.6 replaced with the minimum over all seven of
    :data:`~neurostim.safety.LIMIT_BEARING` -- so the artist annotated
    ``binding limit 141.3 µA`` beside a report headline of ``20.00`` on the package's own
    worked example, a factor of 7.07 in the permissive direction (ledger 1, 48). A figure
    and a report go into the same manuscript; they do not get to disagree.

    Every limit-bearing check that ran is drawn, labelled with its own name, so the
    mechanism the annotation names is a curve the reader can find. A ceiling does not move
    with the requested amplitude -- that is what makes it a ceiling -- so each is a flat
    line and the assessment is run once rather than once per sampled current.

    When no amplitude is safe at all -- a monophasic protocol FAILs charge balance at
    every amplitude, being a property of the waveform rather than of the current -- the
    rule and its number are replaced by the sentence naming the check, not printed beside
    it (ledger 84). The per-check ceilings stay: each is that check's own honest limit and
    carries that check's name.
    """
    apply_style()
    if ax is None:
        _, ax = subplots(width_mm=SINGLE_COLUMN_MM, height_mm=62.0)

    calc = SafetyCalculator(
        electrode, protocol, compliance_V=compliance_V, **calculator_kwargs
    )
    assessment = calc.assess()
    ceilings = [
        (check.name, check.ceiling_uA)
        for check in assessment.checks
        if check.name in LIMIT_BEARING and math.isfinite(check.ceiling_uA)
    ]

    if currents_uA is None:
        highest = max((ceiling for _, ceiling in ceilings), default=protocol.current_uA)
        top = highest * 1.6
        currents_uA = np.logspace(
            math.log10(max(top * 1e-3, 1e-3)), math.log10(top), 120
        )
    currents = np.asarray(list(currents_uA), dtype=float)

    ax.loglog(currents, currents, color=PALETTE["light_grey"], linewidth=0.8,
              linestyle=":", label="requested", zorder=1)
    for index, (name, ceiling_uA) in enumerate(ceilings):
        lap, colour = divmod(index, len(CATEGORICAL))
        ax.loglog(
            currents,
            np.full_like(currents, ceiling_uA),
            color=CATEGORICAL[colour],
            linestyle="-" if lap == 0 else "--",
            label=name,
        )

    binding_uA = assessment.limiting_current_uA
    if binding_uA is None:
        refusal = assessment.no_safe_amplitude_note()
        # In place of the amplitude, not beside it: a reader who sees a number will
        # programme it, however the sentence next to it is worded. The shaded region goes
        # with it, for the same reason -- it is a claim that everything below is safe.
        # Low in the panel, where the ceilings are not, and in the corner the other
        # figures here put their caveats.
        ax.text(
            0.03,
            0.04,
            textwrap.fill(refusal, 44),
            transform=ax.transAxes,
            fontsize=6,
            color=PALETTE["fail"],
            va="bottom",
        )
    else:
        ax.fill_between(currents, binding_uA, currents.min(), color=PALETTE["pass"],
                        alpha=0.07, linewidth=0, zorder=0)
        ax.axhline(binding_uA, color=PALETTE["fail"], linewidth=0.7, linestyle="-",
                   alpha=0.6)
        ax.annotate(
            f"binding limit {format_limit(binding_uA)} µA\n"
            f"({assessment.limiting_mechanism})"
            + (", provisional" if assessment.limit_is_provisional else ""),
            xy=(currents[0], binding_uA),
            xytext=(2, 3),
            textcoords="offset points",
            fontsize=6,
            color=PALETTE["fail"],
        )

    ax.set_xlabel("Requested current (µA)")
    ax.set_ylabel("Permitted current (µA)")
    ax.set_title(f"Amplitude limits, {electrode.material}", pad=4)
    # Every candidate is a horizontal line spanning the full width, so an unframed legend
    # sits on top of several of them and neither reads. This is the one legend in the
    # module that needs to occlude rather than float.
    ax.legend(loc="lower right", handlelength=1.6, fontsize=5.4, frameon=True,
              framealpha=0.92, facecolor="white", edgecolor="none")
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
    bars = ax.barh(y, limits, color=colours, height=0.62, linewidth=0)
    # A failing bar is hatched as well as red (ledger 56): colour alone does not survive
    # greyscale printing or a colour-blind reader.
    for bar, limit in zip(bars, limits, strict=True):
        if limit < applied:
            bar.set_hatch("////")
            bar.set_edgecolor("white")
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

    Every panel is drawn at ``calc``'s own settings. Panel (b) used to take only the
    electrode, the protocol and the compliance voltage, so its three curves were
    recomputed at the library defaults, and panel (d) drew the field at the library's
    0.35 S/m whatever conductivity the verdict above it was computed with (ledger 48).
    The settings come from :func:`_calculator_settings`, which reads the constructor
    rather than a list, so a setting added later cannot be forgotten here.
    """
    apply_style()
    fig, axes = subplots(2, 2, width_mm=width_mm, height_mm=115.0)
    (ax_a, ax_b), (ax_c, ax_d) = axes

    shannon_safe_operating_area(calc, ax=ax_a)
    panel_label(ax_a, "a")

    settings = _calculator_settings(calc)
    if compliance_V is not None:
        settings["compliance_V"] = compliance_V
    current_limit_sweep(calc.e, calc.p, ax=ax_b, **settings)
    panel_label(ax_b, "b")

    material_comparison(calc.e, calc.p, ax=ax_c, policy=calc.policy)
    panel_label(ax_c, "c")

    radial_field_profile(
        calc.p.current_uA,
        calc.e,
        ax=ax_d,
        sigma_S_per_m=calc.tissue_conductivity_S_per_m,
    )
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
