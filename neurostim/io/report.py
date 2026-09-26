"""Methods-ready PDF safety reports.

The output is designed to be attachable to a methods section or an ethics submission:
it states the electrode, the protocol, every computed limit, the *conditions under
which each literature constant was measured*, and a bibliography of the primary sources.
A report that gives a number without its provenance is not much use in a methods
section, which is why the conditions column is not optional here.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .. import _repro
from ..references import cite
from ..safety import SafetyCalculator
from ..safety._limits import format_exceeding, format_limit
from ..safety.assessment import SafetyAssessment, Status
from ..safety.compliance import ComplianceResult

_STATUS_HEX = {
    Status.PASS: "#1a7f37",
    Status.CAUTION: "#9a6700",
    Status.FAIL: "#b62324",
    Status.NOT_EVALUATED: "#57606a",
}

_STATUS_COLOUR = {status: colors.HexColor(hexcode) for status, hexcode in _STATUS_HEX.items()}

_CORE_REFERENCE_KEYS = (
    "shannon1992",
    "mccreery1990",
    "merrill2005",
    "cogan2008",
    "newman1966",
)
"""Methodological sources every report rests on, cited or not.

These describe the criteria the report applies rather than any one material, so they
belong in the bibliography even when their keys never appear in the body text.
"""


def _potential_scale(calc: SafetyCalculator) -> str:
    """What the peak electrode potential is measured against.

    Not every material's limits are absolute potentials on a reference scale. 316LVM's
    are a polarisation magnitude relative to rest, which is why ``WaterWindow`` carries
    a ``scale``. Printing a hardcoded "vs Ag|AgCl" beside it would state something the
    source did not measure.
    """
    window = calc.material.water_window
    return window.scale if window is not None else "vs the resting potential"


def _reference_keys(calc: SafetyCalculator, assessment: SafetyAssessment) -> list[str]:
    """Every source this particular report cites, in registry order.

    Built by scanning the assembled text rather than kept as a hand-maintained list.
    A fixed list goes stale silently: two sources named in the body -- Butterwick's
    electroporation threshold and Kuncel & Grill's current-distribution result -- were
    being discussed in real output with no bibliography entry. In a report whose whole
    claim is traceable provenance, a dangling citation is the one defect that matters
    most, and it is the kind a human proof-read will miss.
    """
    from ..references import REFERENCES

    haystack = "\n".join(
        [
            assessment.describe(),
            calc.material.describe(),
            calc.material.cic.describe(),
            *(c.detail + c.summary for c in assessment.checks),
        ]
    )
    keys = set(_CORE_REFERENCE_KEYS)
    for key, ref in REFERENCES.items():
        if key == "user_measurement":
            continue
        # Two ways a source gets named. Provenance strings carry the bare key --
        # "(riedy_walter1996)". Prose carries the author and year -- "Butterwick et al.
        # (2007)". Matching only the key missed every prose citation, which is how the
        # two dangling entries arose. The surname is taken from the reference record
        # rather than written out here, so a new source is picked up automatically.
        surname = ref.authors.split(",")[0].split()[0]
        near_year = rf"{re.escape(surname)}[^\n]{{0,40}}{ref.year}"
        if key in haystack or re.search(near_year, haystack):
            keys.add(key)
    return [k for k in REFERENCES if k in keys]


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "nsTitle", parent=base["Title"], fontSize=16, spaceAfter=2 * mm
        ),
        "h2": ParagraphStyle(
            "nsH2",
            parent=base["Heading2"],
            fontSize=11,
            spaceBefore=5 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "nsBody", parent=base["BodyText"], fontSize=8.5, leading=11.5
        ),
        "small": ParagraphStyle(
            "nsSmall",
            parent=base["BodyText"],
            fontSize=7.2,
            leading=9.5,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#57606a"),
        ),
        "mono": ParagraphStyle(
            "nsMono",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=7.4,
            leading=9.5,
        ),
    }


def _kv_table(
    rows: list[tuple[str, str]], styles, widths=(58 * mm, 108 * mm)
) -> Table:
    """Two-column table whose value cells are Paragraphs, not raw strings.

    Raw strings in a ReportLab table cell are drawn verbatim on one line: HTML entities
    are not decoded and overlong text is clipped at the column edge rather than wrapped.
    Both showed up in real output -- "314 &micro;m" printed literally, and a provenance
    row truncated mid-word at "on 0.016 cm^2, geo". Wrapping the value in a Paragraph
    fixes both. The key column stays a plain string so the table-level bold FONTNAME
    still applies to it.
    """
    table = Table(
        [[k, Paragraph(v, styles["body"])] for k, v in rows],
        colWidths=list(widths),
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e1e4e8")),
            ]
        )
    )
    return table


def _checks_table(assessment: SafetyAssessment, styles) -> Table:
    header = ["Check", "Status", "Result"]
    rows = [header]
    for check in assessment.checks:
        rows.append(
            [
                Paragraph(check.name, styles["body"]),
                check.status.value,
                Paragraph(check.summary, styles["body"]),
            ]
        )
    table = Table(rows, colWidths=[38 * mm, 26 * mm, 102 * mm], hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f4f6")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    for i, check in enumerate(assessment.checks, start=1):
        style.append(("TEXTCOLOR", (1, i), (1, i), _STATUS_COLOUR[check.status]))
        style.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
    table.setStyle(TableStyle(style))
    return table


def _required_compliance_text(calc: SafetyCalculator, result: ComplianceResult) -> str:
    """The requirement and a breakdown that adds up, naming the budget it assumes.

    With a counter electrode the counter's own polarisation is a third term; without one
    the single-interface assumption is stated on the row (ledger 5, C3.5). An unbalanced
    train's DC offset is named on the row, electrode by electrode (ledger 140).
    """
    if not math.isfinite(result.required_V):
        # A refusal sentence, not a bare "inf V" (ledger 143).
        return result.unbounded_reason
    text = (
        f"{result.required_V:.3f} V ({result.ohmic_drop_V:.3f} V ohmic + "
        f"{result.polarisation_V:.3f} V polarisation"
    )
    if result.counter_modelled:
        text += f" + {result.counter_polarisation_V:.3f} V counter polarisation"
    if result.offset_factor:
        phase = "return" if result.offset_on_return else "leading"
        text += f"; train DC offset {result.offset_V:.3f} V"
        if result.counter_modelled:
            text += f" + {result.counter_offset_V:.3f} V counter"
        text += f" on the {phase} phase"
    if result.counter_modelled:
        return f"{text}; counter electrode at {calc.counter_separation_um:g} um)"
    return f"{text}; monopolar single-interface budget assumed)"


def _headline_html(assessment: SafetyAssessment) -> str:
    """The PDF's one-line verdict: status, what did not run, the limit and its caveats.

    A limit set by a provisional check is marked here too (ledger 128).
    """
    verdict = (
        f'<font color="{_STATUS_HEX[assessment.status]}">'
        f"<b>{assessment.status.value}</b></font>"
    )
    # The status is the worst verdict among the checks that ran, so the ones that did not
    # run are named beside it rather than left for the reader to spot in the table.
    not_evaluated = assessment.not_evaluated_note()
    # In place of the amplitude, never beside it: a reader who sees a number will
    # programme it whatever the sentence next to it says (ledger 84).
    limit_uA = assessment.limiting_current_uA
    headline = (
        f"<b>{assessment.no_safe_amplitude_note()}</b>"
        if limit_uA is None
        else (
            f"limiting current "
            f"<b>{format_limit(limit_uA)} &micro;A</b> "
            f"({assessment.limiting_mechanism})"
        )
    )
    incomplete = assessment.limits_incomplete_note()
    provisional = assessment.provisional_limit_note()
    return (
        f"Overall assessment: {verdict}"
        + (f" {not_evaluated}" if not_evaluated else "")
        + f" &middot; {headline}"
        + (f" &middot; <b>{provisional}</b>" if provisional else "")
        + (f" &middot; {incomplete}" if incomplete and limit_uA is not None else "")
    )


def _settings_rows(calc: SafetyCalculator) -> list[tuple[str, str]]:
    """Every calculator setting, one row each (ledger 54).

    The PDF rendered 4 of the 11, so two reports that differed only in the resting
    potential or the lead resistance had identical settings beside different results.
    Built from the same record the JSON and the audit use.
    """
    from .tabular import calculator_settings

    settings = calculator_settings(calc, counter_always=True)

    def text(value: object, unit: str = "", absent: str = "not supplied") -> str:
        return absent if value is None else f"{value:g}{unit}" if isinstance(
            value, float
        ) else str(value)

    counter = (
        "none (monopolar single-interface budget)"
        if calc.counter_electrode is None
        else f"{calc.counter_electrode.describe()} at {calc.counter_separation_um:g} "
        f"&micro;m"
    )
    return [
        ("Shannon k", text(settings["shannon_k"])),
        ("CIC policy", str(settings["cic_policy"])),
        ("Medium", str(settings["medium"])),
        ("Tissue conductivity", text(settings["tissue_conductivity_S_per_m"], " S/m")),
        ("Lead resistance", text(settings["lead_resistance_ohm"], " &ohm;")),
        ("Compliance voltage", text(settings["compliance_V"], " V")),
        ("Measured impedance", text(settings["measured_impedance_ohm"], " &ohm;")),
        ("Resting potential", text(settings["resting_potential_V"], " V")),
        (
            "Interfacial capacitance",
            text(settings["capacitance_uF_cm2"], " &micro;F/cm&sup2;",
                 absent="derived from the material's CIC and window"),
        ),
        ("Counter electrode", counter),
    ]


def _reproducibility_rows(calc: SafetyCalculator) -> list[tuple[str, str]]:
    """The package version and the audit digest over inputs and constants (ledger 54).

    ``neurostim.audit`` already built this record; the PDF never called it, so a printed
    report could not be reproduced from its own face.
    """
    from .. import audit

    record = audit.record(calc)
    return [
        ("Package version", record.package_version),
        ("Digest", record.digest),
    ]


def _computed_rows(
    calc: SafetyCalculator, assessment: SafetyAssessment
) -> list[tuple[str, str]]:
    """The PDF's "Computed quantities" rows.

    A quantity derived from an unverified charge-injection limit says PROVISIONAL, as the
    Charge injection row does: the peak potential and the required compliance both rest
    on the capacitance that limit sets (ledger 60).
    """
    # An applied value above its bound gains digits until it reads above it, as the check
    # summaries do: these rows printed charge density "100" beside a limit "100.0"
    # (ledger 50).
    charge = assessment.charge
    cic_text = format_limit(charge.cic_limit_uC_cm2)
    density_text = (
        format_exceeding(charge.charge_density_uC_cm2, cic_text)
        if charge.charge_density_uC_cm2 > charge.cic_limit_uC_cm2
        else f"{charge.charge_density_uC_cm2:.4g}"
    )
    k_text = f"{assessment.shannon.k_metric:.3f}"
    if assessment.shannon.k_metric > calc.k and float(k_text) <= float(f"{calc.k:.2f}"):
        k_text = format_exceeding(assessment.shannon.k_metric, f"{calc.k:.2f}")
    rows: list[tuple[str, str]] = [
        (
            "Charge density",
            f"{density_text} &micro;C/cm&sup2; per phase",
        ),
        (
            "Shannon k",
            f"{k_text} "
            f"(threshold {calc.k:.2f}; Shannon 1992, Merrill 2005 eq. 5.1)",
        ),
        (
            "Shannon current limit",
            f"{format_limit(assessment.shannon.max_current_uA)} &micro;A",
        ),
        (
            "Charge-injection limit",
            f"{cic_text} "
            f"&micro;C/cm&sup2; "
            f"({calc.policy} policy)",
        ),
        (
            "Charge-injection current limit",
            f"{format_limit(assessment.charge.max_current_uA)} &micro;A",
        ),
        (
            "Peak electrode potential",
            f"{assessment.water_window.peak_potential_V:+.3f} V "
            f"{_potential_scale(calc)}",
        ),
        (
            "Required compliance",
            _required_compliance_text(calc, assessment.compliance),
        ),
    ]
    marked = {
        "Peak electrode potential": assessment.water_window.capacitance_provisional,
        "Required compliance": assessment.compliance.capacitance_provisional,
    }
    return [
        (label, f"{value} PROVISIONAL" if marked.get(label) else value)
        for label, value in rows
    ]


def _provenance_rows(
    calc: SafetyCalculator, assessment: SafetyAssessment
) -> list[tuple[str, str]]:
    """The PDF's "Provenance of applied limits" rows, one per applied constant.

    The chronic threshold has a row of its own, with its PROVISIONAL flag when it is not
    confirmed (ledger 30); it used to be applied with no provenance row at all.
    """
    prov: list[tuple[str, str]] = [
        ("Charge-injection limit", calc.material.cic.describe()),
    ]
    if calc.material.water_window is not None:
        window = calc.material.water_window.describe()
        if assessment.water_window.capacitance_provisional:
            # The limits are the source's; the headroom beside them came off the user's
            # unverified CIC through C_eff (ledger 60).
            window += "; the excursion within it uses C_eff from an unverified CIC"
        prov.append(("Water window", window))
    else:
        prov.append(
            ("Water window", "no potential limits on record for this material")
        )
    if calc.material.chronic_threshold is not None:
        prov.append(
            ("Chronic degradation threshold", calc.material.chronic_threshold.describe())
        )
    else:
        prov.append(
            (
                "Chronic degradation threshold",
                "no chronic threshold on record for this material",
            )
        )
    # The material records carry caveats that nothing rendered. SS316LVM's said the
    # cited work argues its own high end down; it was 576 characters of stored text that
    # never reached a page. A provenance section that omits the source's own reservations
    # about its number is not stating provenance.
    if calc.material.cic.note:
        prov.append(("Limit, as the source states it", calc.material.cic.note))
    if calc.material.note:
        prov.append((f"{calc.material.key} notes", calc.material.note))
    prov.append(
        (
            "Interface model",
            f"{assessment.water_window.interface_model}, "
            f"C_eff = {assessment.water_window.capacitance_uF_cm2:.0f} "
            f"&micro;F/cm&sup2;",
        )
    )
    return prov


def build_report(
    calc: SafetyCalculator,
    path: str | Path,
    *,
    title: str = "Neurostimulation Electrode Safety Report",
    author: str = "",
    notes: str = "",
) -> Path:
    """Render a full safety assessment to a PDF and return the written path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    assessment = calc.assess()
    styles = _styles()
    story: list = []

    story.append(Paragraph(title, styles["title"]))
    stamp = _repro.build_time().strftime("%Y-%m-%d %H:%M UTC")
    byline = f"Generated {stamp}" + (f" &middot; {author}" if author else "")
    story.append(Paragraph(byline, styles["small"]))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(_headline_html(assessment), styles["body"]))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Electrode", styles["h2"]))
    dims = ", ".join(f"{k} = {v:g} &micro;m" for k, v in calc.e.dimensions().items())
    story.append(
        _kv_table(
            [
                ("Geometry", f"{calc.e.shape_name} ({dims})"),
                ("Material", f"{calc.material.name} ({calc.material.key})"),
                ("Geometric area", f"{calc.e.area_cm2:.4g} cm&sup2;"),
                (
                    "Access resistance",
                    # Renders as U+2126 OHM SIGN, not U+03A9 GREEK CAPITAL OMEGA:
                    # the built-in Type 1 Helvetica has no omega, so ReportLab
                    # substitutes a glyph that maps back to U+2126 whichever entity is
                    # used. The two are canonically equivalent under NFKC and look
                    # identical, but they do not compare equal -- normalise before
                    # searching extracted report text for it.
                    f"{assessment.compliance.access_resistance_ohm:.0f} &ohm; "
                    f"({'exact' if calc.e.access_resistance_is_exact else calc.e.substitute_name + ' approximation'}"
                    f", &sigma; = {calc.tissue_conductivity_S_per_m:g} S/m)",
                ),
            ],
            styles,
        )
    )

    story.append(Paragraph("Stimulation protocol", styles["h2"]))
    p = calc.p
    story.append(
        _kv_table(
            [
                ("Waveform", f"{p.waveform}, {p.leading_polarity}-first"),
                ("Amplitude", f"{p.current_uA:g} &micro;A"),
                ("Pulse width", f"{p.pulse_width_us:g} &micro;s"),
                ("Frequency", f"{p.frequency_hz:g} Hz"),
                (
                    "Train",
                    "continuous" if p.n_pulses == float("inf")
                    else f"{p.train_duration_s:g} s ({p.n_pulses:.0f} pulses)",
                ),
                ("Charge per phase", f"{p.charge_per_phase_uC:.4g} &micro;C"),
                ("Duty cycle", f"{p.duty_cycle * 100:.2f} %"),
                ("RMS current", f"{p.rms_current_uA:.4g} &micro;A"),
                # The recovered fraction sits next to the DC it produces: a reader
                # looking at a non-zero "Net DC" needs the setting that caused it on the
                # same page, not inferred from the difference of two charges.
                ("Charge recovery", f"{p.charge_recovery_ratio * 100:.1f} %"),
                ("Net DC", f"{p.net_dc_current_uA:.4g} &micro;A"),
            ],
            styles,
        )
    )

    story.append(Paragraph("Settings", styles["h2"]))
    story.append(_kv_table(_settings_rows(calc), styles))
    story.append(Paragraph("Reproducibility", styles["h2"]))
    story.append(_kv_table(_reproducibility_rows(calc), styles))

    story.append(Paragraph("Safety checks", styles["h2"]))
    story.append(_checks_table(assessment, styles))

    story.append(Paragraph("Computed quantities", styles["h2"]))
    story.append(_kv_table(_computed_rows(calc, assessment), styles))

    story.append(Paragraph("Provenance of applied limits", styles["h2"]))
    story.append(_kv_table(_provenance_rows(calc, assessment), styles))


    warnings = [c for c in assessment.checks if c.status in (Status.FAIL, Status.CAUTION)]
    if warnings:
        story.append(Paragraph("Warnings and caveats", styles["h2"]))
        for check in warnings:
            detail = check.detail.replace("\n", "<br/>")
            story.append(
                KeepTogether(
                    [
                        Paragraph(
                            f"<b>{check.status.value} &mdash; {check.name}:</b> "
                            f"{check.summary}",
                            styles["body"],
                        ),
                        Paragraph(detail, styles["mono"]),
                        Spacer(1, 2 * mm),
                    ]
                )
            )

    if notes:
        story.append(Paragraph("Notes", styles["h2"]))
        story.append(Paragraph(notes.replace("\n", "<br/>"), styles["body"]))

    story.append(PageBreak())
    story.append(Paragraph("References", styles["h2"]))
    for key in _reference_keys(calc, assessment):
        story.append(Paragraph(f"[{key}] {cite(key).citation()}", styles["body"]))
        story.append(Spacer(1, 1.2 * mm))

    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            "<b>Limitations.</b> This report is not a validated clinical or regulatory "
            "device calculation. The Shannon criterion is an empirical separatrix fitted "
            "to animal histology, largely from cortical electrodes at frequencies below "
            "those used clinically. Charge-injection limits are pulse-width, waveform and "
            "electrolyte dependent and are quoted here at their published measurement "
            "conditions with no scaling applied. The water-window check derives the "
            "interfacial capacitance from the material's own charge-injection limit and "
            "window, so injecting that limit reaches the window edge by construction; it "
            "is therefore not an independent test of charge density, and what it adds is "
            "the effect of a non-zero resting potential or interpulse bias. Verify all "
            "limits against characterisation of your own electrodes before use.",
            styles["small"],
        )
    )

    SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title,
        author=author or "neurostim",
        # Pins reportlab's /CreationDate, /ModDate and document id when the build date is
        # pinned, so a committed report diffs to nothing. Left off otherwise, because
        # invariant mode would stamp a fixed, false date on an ordinary report.
        invariant=1 if _repro.is_pinned() else 0,
    ).build(story)
    return out
