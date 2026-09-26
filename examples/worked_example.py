"""End-to-end worked example.

Runs the whole pipeline on a real question: a 330/270 um guide-cannula ring electrode,
80 uA at 200 us and 130 Hz. Prints the assessment, finds the usable amplitude, compares
materials, estimates heating and activation, and writes a PDF report plus figures.

Run with::

    python examples/worked_example.py [output_directory]

Outputs are written to the given directory (default: ./example_output) and are never
opened automatically.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np

from neurostim import (
    CylindricalBandElectrode,
    RingElectrode,
    SafetyCalculator,
    StimProtocol,
    get_material,
    with_measured_cic,
)
from neurostim.io import build_report, current_sweep, report_to_json, write_csv
from neurostim.models import strength_duration as sd
from neurostim.models import thermal, vta
from neurostim.safety._limits import format_limit
from neurostim.viz import safety_summary, save_publication, strength_duration


def rule(title: str) -> None:
    print(f"\n{'=' * 76}\n{title}\n{'=' * 76}")


def main(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    electrode = RingElectrode(330, 270, "Pt")
    protocol = StimProtocol(80, 200, 130, 1)
    calc = SafetyCalculator(electrode, protocol, compliance_V=10.0)

    rule("1. Full assessment")
    print(calc.describe())

    rule("2. What amplitude is actually usable?")
    assessment = calc.assess()
    # Every amplitude below is a maximum, so it is floored rather than rounded to
    # nearest: `:.4g` printed the charge-injection ceiling 141.37166941154072 as
    # "141.4 uA", and programming 141.4 uA FAILs the check whose maximum it claims to be
    # (ledger 49). `format_limit` is the same renderer the report, the PDF, the GUI and
    # the figure use.
    print(f"Requested:        {protocol.current_uA:g} uA")
    # `limiting_current_uA` is None exactly when no amplitude is safe, so the refusal is
    # printed in place of a number rather than beside one (ledger 84, 89).
    limit_uA = assessment.limiting_current_uA
    binding = (
        f"none -- {assessment.unsafe_at_any_amplitude_note()}"
        if limit_uA is None
        else f"{format_limit(limit_uA)} uA"
    )
    print(f"Binding limit:    {binding}")
    print(f"Set by:           {assessment.limiting_mechanism}")
    print(f"Shannon allows:   {format_limit(assessment.shannon.max_current_uA)} uA")
    print(f"Electrode allows: {format_limit(assessment.charge.max_current_uA)} uA")
    # Read off the assessment, not written beside it: a fixed sentence here claimed the
    # tissue criterion was "satisfied with 7x headroom" eleven lines after the script's
    # own "[NOT_EVALUATED] Shannon criterion" (ledger 61/M10).
    shannon = next(c for c in assessment.checks if c.name == "Shannon criterion")
    if shannon.status.value == "NOT_EVALUATED":
        gap = (
            "The Shannon criterion does not apply at this size, so its number above is "
            f"not a limit. The binding limit is set by {assessment.limiting_mechanism}: "
            "on a microelectrode the charge per phase, not the charge density, governs "
            "damage."
        )
    else:
        gap = (
            f"Shannon allows {assessment.shannon.max_current_uA / protocol.current_uA:.1f}x "
            f"the requested amplitude; the binding limit is set by "
            f"{assessment.limiting_mechanism}. Passing Shannon alone is not sufficient."
        )
    print("\n" + textwrap.fill(gap, 76))

    rule("3. Current sweep")
    sweep = current_sweep(electrode, protocol, np.arange(10, 121, 10), compliance_V=10.0)
    print(
        sweep[["current_uA", "charge_density_uC_cm2", "status", "limiting_mechanism"]]
        .to_string(index=False)
    )
    write_csv(sweep, output_dir / "current_sweep.csv")

    rule("4. Would another material help?")
    print(
        f"  {'material':10s} {'CIC limit':>12s}  {'status':<8s} {'max uA':>8s}  "
        f"binding constraint / first failure"
    )
    bound: dict[str, tuple[float | None, str]] = {}
    for key in ("Pt", "SIROF", "PEDOT", "SS316LVM"):
        material = get_material(key)
        result = SafetyCalculator(
            electrode, protocol, material=material, compliance_V=10.0
        ).assess()
        bound[key] = (result.limiting_current_uA, result.limiting_mechanism)
        failing = result.failed
        reason = failing[0].name if failing else result.limiting_mechanism
        material_limit_uA = result.limiting_current_uA
        rendered = (
            "none" if material_limit_uA is None else format_limit(material_limit_uA)
        )
        print(
            f"  {key:10s} "
            f"{format_limit(material.cic_uC_cm2('conservative')):>8s} uC/cm^2  "
            f"{result.status.value:<8s} "
            f"{rendered:>8s}  {reason}"
        )
    # Also read off the results: this paragraph used to say the interface was driven
    # 2.8 V from rest and "leaves every published water window" beside the script's own
    # "[PASS] Water window: peak -0.23 V" (ledger 61/M10).
    pt_cic = get_material("Pt").cic_uC_cm2("conservative")
    higher = [k for k in bound if get_material(k).cic_uC_cm2("conservative") > pt_cic]
    shared = {bound[k] for k in (*higher, "Pt")}
    if higher and len(shared) == 1:
        limit_uA, mechanism = shared.pop()
        rendered = "no amplitude" if limit_uA is None else f"{format_limit(limit_uA)} uA"
        verdict = (
            "A higher charge-injection limit does not rescue this protocol: every "
            f"material here with a higher limit than Pt ({', '.join(higher)}) is bound "
            f"at {rendered} by {mechanism}, as Pt is"
            + (
                ", a check on charge per phase that no electrode material changes. "
                "Lower the charge per phase -- shorter pulse or lower amplitude -- "
                "rather than changing material."
                if mechanism == "Microelectrode charge/phase"
                else "."
            )
        )
        print("\n" + textwrap.fill(verdict, 76))
    else:
        print("\nThe materials bind differently here; see the table above.")
    print("\nProvenance for the best-performing material:")
    print(get_material("SIROF").describe())

    rule("5. Using your own characterisation instead of the literature")
    measured = with_measured_cic(
        get_material("Pt"), 62.0, pulse_width_us=200,
        note="voltage-transient measurement, hypothetical batch",
    )
    print(measured.cic.describe())
    measured_max_uA = SafetyCalculator(
        electrode, protocol, material=measured
    ).max_current_cic_uA
    print(f"  max current with measured limit: {format_limit(measured_max_uA)} uA")

    rule("6. Clinical DBS contact, for contrast")
    dbs = CylindricalBandElectrode(1270, 1500, "PtIr")
    dbs_protocol = StimProtocol(3000, 60, 130, 1)
    dbs_calc = SafetyCalculator(dbs, dbs_protocol, compliance_V=10.0)
    dbs_assessment = dbs_calc.assess()
    print(f"Contact area:   {dbs.area_cm2:.4f} cm^2 (Cogan 2008 quotes 0.06 cm^2)")
    print(f"Charge/phase:   {dbs_protocol.charge_per_phase_uC:.3f} uC")
    print(f"Charge density: {dbs_assessment.charge.charge_density_uC_cm2:.2f} uC/cm^2")
    print(f"Status:         {dbs_assessment.status.value}")
    print(f"Limiting:       {dbs_assessment.limiting_mechanism}")

    rule("7. Tissue heating")
    resistance = dbs.access_resistance_ohm(0.35)
    heat = thermal.evaluate(
        dbs_protocol.rms_current_uA, resistance, dbs.equivalent_radius_um
    )
    print(heat.describe())
    print(
        "\nThis is well below the ~0.8 K peak Elwassif et al. (2006) obtain from a full\n"
        "finite element model that includes lead and electrode self-heating. The gap is\n"
        "not reconciled; treat this as an order-of-magnitude floor."
    )

    rule("8. Strength-duration, fitted to measured thresholds")
    widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
    thresholds = np.array([82.0, 50.0, 34.0, 26.0, 22.0])
    fit = sd.fit_weiss(widths, thresholds)
    print(fit.describe())
    print(
        "\nThreshold charge rises with pulse width, so short pulses minimise injected\n"
        "charge. Efficacy and charge-based safety limits point the same way."
    )

    rule("9. Activation estimate (weakest model - read the caveats)")
    activation = vta.evaluate(
        protocol.current_uA, electrode_radius_um=electrode.equivalent_radius_um
    )
    print(activation.describe())

    rule("10. Outputs")
    pdf = build_report(
        calc,
        output_dir / "safety_report.pdf",
        author="worked example",
        notes="Generated by examples/worked_example.py.",
    )
    print(f"  PDF report      {pdf}")

    json_path = output_dir / "assessment.json"
    report_to_json(calc, json_path)
    print(f"  JSON            {json_path}")

    fig, _ = safety_summary(calc)
    # SVG and PDF only: the vector formats are the deliverable. The 600 dpi TIFF that
    # `save_publication` also offers is about 1 MB of LZW-compressed RGB for this figure.
    for path in save_publication(
        fig, output_dir / "figure_summary", formats=("svg", "pdf"), close=True
    ):
        print(f"  figure          {path}")

    strength_duration(fit.rheobase_uA, fit.chronaxie_us)
    import matplotlib.pyplot as plt

    for path in save_publication(
        plt.gcf(), output_dir / "figure_strength_duration", formats=("svg", "pdf"), close=True
    ):
        print(f"  figure          {path}")

    print(f"\n  CSV             {output_dir / 'current_sweep.csv'}")
    print("\nDone. Nothing was opened automatically.")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("example_output")
    raise SystemExit(main(target))
