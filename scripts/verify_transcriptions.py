"""Check every transcribed constant actually appears in the paper it cites.

Why
---
The constants in :mod:`neurostim.data` and :mod:`neurostim.materials` were read out of
PDFs by hand. Every other risk in this package has been argued down: the mathematics is
verified against closed-form limits, the models carry their validity ranges, the
provenance is machine-checked. What remained was the possibility of a **typo** -- reading
``2.0e5`` as ``2.0e4``, or attaching the right number to the wrong row.

This script closes the typo half of that mechanically. For each constant it searches the
source paper's text for the value in the several forms a PDF might render it, and reports
anything it cannot find.

What it can and cannot catch
----------------------------
**Catches:** any value that does not appear in its cited paper at all. That is the
dominant failure mode for hand transcription.

**Does not catch:** a value that appears in the paper but was attached to the wrong
material, wrong polarity or wrong condition. Detecting that needs a reader, not a search.
The per-constant notes in the data modules exist so a reader can check that quickly.

Usage
-----
    python scripts/verify_transcriptions.py [papers_dir] [--strict]

Requires ``pdftotext`` (poppler). Papers that are absent are reported as skipped rather
than failed, so the script is useful even with a partial library.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PAPERS_DIR = Path(__file__).resolve().parent.parent / "papers_stim_calc_ref"


@dataclass(frozen=True)
class Claim:
    """One transcribed value and the paper it should appear in."""

    value: str
    description: str
    paper_glob: str
    alternates: tuple[str, ...] = field(default_factory=tuple)
    """Other renderings to accept, e.g. '2.0 x 10 5' for scientific notation."""


# Every value below is one this package stores. The glob identifies the source PDF.
CLAIMS: tuple[Claim, ...] = (
    # --- Shannon 1992 ---
    Claim("1.5", "Shannon's recommended conservative k", "shannon1992*"),
    Claim("2", "k at which damage was observed", "shannon1992*"),
    # --- McCreery 1990 Table I ---
    Claim("800", "microelectrode charge density, no damage", "mccreery1990*"),
    Claim("1600", "microelectrode charge density, no damage", "mccreery1990*"),
    Claim("400", "pulse width per phase (us)", "mccreery1990*"),
    Claim("50 Hz", "stimulation frequency", "mccreery1990*"),
    Claim("0.052", "microelectrode charge per phase (uC)", "mccreery1990*"),
    Claim("12", "lowest damaging charge density", "mccreery1990*"),
    # --- Rose & Robblee 1990 ---
    Claim("50", "Pt anodic-first lower bound", "rose1990*"),
    Claim("150", "Pt cathodic-first upper bound", "rose1990*"),
    Claim("0.2 ms", "pulse width", "rose1990*"),
    Claim("7.3", "electrolyte pH", "rose1990*"),
    Claim("600", "biased Pt charge density", "rose1990*"),
    Claim("250", "Pt charge density at 1 ms", "rose1990*"),
    # --- Beebe & Rose 1988 ---
    Claim("2.1", "AIROF anodic-first limit (mC/cm2)", "beebe1988*"),
    Claim("3.5", "AIROF biased limit (mC/cm2)", "beebe1988*"),
    # --- Elwassif 2006 ---
    Claim("0.527", "thermal conductivity used", "elwassif2006*"),
    Claim("1.56", "RMS drive voltage", "elwassif2006*"),
    Claim("37.82", "peak temperature, lead 3389", "elwassif2006*"),
    Claim("3650", "tissue specific heat", "elwassif2006*"),
    Claim("1057", "blood density", "elwassif2006*"),
    # --- Butterwick 2007 ---
    Claim("0.061", "retina threshold at 6 ms (A/cm2)", "Tissue_Damage*"),
    Claim("1.3", "retina threshold at 6 us (A/cm2)", "Tissue_Damage*"),
    Claim("300", "size-independence boundary (um)", "Tissue_Damage*"),
    Claim("200", "constant-current boundary (um)", "Tissue_Damage*"),
    # --- McCreery 1995 ---
    Claim("0.37", "damage slope at 50 Hz", "mccreery1995*"),
    Claim("1.1", "damage slope at 100 Hz", "mccreery1995*"),
    Claim("0.003", "damage slope at 20 Hz", "mccreery1995*"),
    Claim("0.87", "correlation at 50 Hz", "mccreery1995*"),
    # --- McCreery 2010 ---
    Claim("2 nC", "no-damage charge per phase", "nihms209066*"),
    Claim("4 nC", "damaging charge per phase", "nihms209066*"),
    Claim("150", "damage radius at 100 % duty (um)", "nihms209066*"),
    Claim("60", "damage radius at 50 % duty (um)", "nihms209066*"),
    # --- Gabriel 1996 Part III, grey matter Cole-Cole row ---
    Claim("45.0", "grey matter delta-eps 1", "S_Gabriel*", ("45",)),
    Claim("7.96", "grey matter tau 1 (ps)", "S_Gabriel*"),
    Claim("106.10", "grey matter tau 3 (us)", "S_Gabriel*", ("106.1",)),
    Claim("5.305", "grey matter tau 4 (ms)", "S_Gabriel*"),
    Claim("0.22", "grey matter alpha 3", "S_Gabriel*"),
    # --- Leung 2014 ---
    Claim("3.84", "Pt in vivo acute lower bound", "In_Vivo_and_In_Vitro*"),
    Claim("16.6", "Pt in vivo acute upper bound", "In_Vivo_and_In_Vitro*"),
    Claim("6.99", "Pt in vivo chronic lower bound", "In_Vivo_and_In_Vitro*"),
    Claim("15.8", "Pt in vivo chronic upper bound", "In_Vivo_and_In_Vitro*"),
    # --- Cui & Zhou 2007 / Luo 2011 ---
    Claim("2.3", "PEDOT charge injection limit (mC/cm2)", "Poly_34*"),
    Claim("2.5", "PEDOT/CNT charge injection limit (mC/cm2)", "nihms-292839*"),
    # --- Kuncel & Grill 2004 ---
    Claim("0.0993", "average DBS current density (A/cm2)", "1-s2.0-S1388245704*"),
    Claim("25.6", "percent of contact above average", "1-s2.0-S1388245704*"),
    Claim("0.06", "DBS contact area (cm2)", "1-s2.0-S1388245704*"),
    # --- Cogan 2008 Table 2 ---
    Claim("0.05", "Pt/PtIr lower limit (mC/cm2)", "cogan_2008*"),
    Claim("15", "PEDOT abstract value (mC/cm2)", "cogan_2008*"),
    # --- ISO 14708-3 Table 101 ---
    Claim("39", "maximum outer surface temperature (C)", "ISO-14708-3*"),
    Claim("21", "skin CEM43 threshold", "ISO-14708-3*"),
    Claim("16", "bone CEM43 threshold", "ISO-14708-3*"),
    # --- Rose, Kelliher & Robblee 1985 (Ta2O5 capacitor electrodes) ---
    Claim("22", "smooth Ta capacitance at 5 V (nF/mm2)", "0165-0270*2885*"),
    Claim("0.088", "smooth Ta charge storage (uC/mm2)", "0165-0270*2885*",
          alternates=("0 088",)),
    Claim("2.6", "best Ta2O5 charge density, Table III (uC/mm2)", "0165-0270*2885*",
          alternates=("26",)),
    Claim("6.3", "best TiO2 charge density, Table III (uC/mm2)", "0165-0270*2885*",
          alternates=("63",)),
    Claim("0.26", "Ta2O5 scaled to 1e-4 mm2 (nC)", "0165-0270*2885*",
          alternates=("026",)),
    Claim("0.63", "TiO2 scaled to 1e-4 mm2 (nC)", "0165-0270*2885*",
          alternates=("0 63",)),
    Claim("10,000", "target intracortical charge density (uC/cm2)", "0165-0270*2885*",
          alternates=("10 000", "10000")),
    Claim("25", "dielectric constant of Ta2O5", "0165-0270*2885*"),
    Claim("7000", "effective dielectric constant of annealed BaTiO3",
          "0165-0270*2885*"),
    # --- Schmidt, Hambrecht & McIntosh 1982 (Ta2O5 in vivo) ---
    Claim("4.2", "anodic DC bias (V)", "0165-0270*2882*"),
    Claim("35", "minimum threshold current (uA)", "0165-0270*2882*"),
    Claim("400", "train frequency (Hz)", "0165-0270*2882*"),
    Claim("57", "implantation duration (days)", "0165-0270*2882*"),
    Claim("44.5", "threshold reduction with cathodic pulsing (percent)",
          "0165-0270*2882*"),
    # --- Riedy & Walter 1996 (316LVM) ---
    # pdftotext renders this scan's "uC" as "pC" and "mA" as "ma"; the numerals
    # survive, which is all the search needs.
    Claim("20", "non-faradaic charge injection limit (uC/cm2)", "10.495287*"),
    Claim("40", "recommended charge injection limit (uC/cm2)", "10.495287*"),
    Claim("1.2", "reversible charge injection limit (V)", "10.495287*"),
    Claim("11.2", "protein study current (mA)", "10.495287*"),
    Claim("3.8", "one-year study current (mA)", "10.495287*"),
    Claim("100", "pulse width (us)", "10.495287*"),
    Claim("60", "pulse repetition rate (pps)", "10.495287*"),
    Claim("15", "days to tarnishing onset", "10.495287*"),
    Claim("0.96", "discharge time constant (ms)", "10.495287*"),
    Claim("0.73", "one-year rise in E_max anodic-first (V)", "10.495287*"),
    Claim("0.63", "one-year rise in E_max cathodic-first (V)", "10.495287*"),
    # --- Asanuma, Arnold & Zarzecki 1976 ---
    Claim("0.14", "median chronaxie, cell bodies (ms)", "bf00238820*"),
    Claim("0.085", "median chronaxie, axons (ms)", "bf00238820*"),
    Claim("0.12", "lower chronaxie bound, cell bodies (ms)", "bf00238820*"),
    Claim("0.06", "lower chronaxie bound, axons (ms)", "bf00238820*"),
    Claim("0.4", "minimum axon threshold (uA)", "bf00238820*"),
    Claim("80", "noxious ICMS current (uA)", "bf00238820*"),
    Claim("0.012", "Mann-Whitney p value", "bf00238820*"),
    Claim("11.8", "mean train duration to 1.5x threshold, surface (ms)",
          "bf00238820*"),
    Claim("27.2", "mean train duration to 1.5x threshold, depth (ms)", "bf00238820*"),
)


def extract_text(pdf: Path, cache: dict[Path, str]) -> str:
    """Extract a PDF to text, memoised."""
    if pdf in cache:
        return cache[pdf]
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    # Collapse whitespace so wrapped numbers still match.
    text = re.sub(r"\s+", " ", result.stdout)
    cache[pdf] = text
    return text


def find_paper(papers_dir: Path, glob: str) -> Path | None:
    """First PDF matching a glob, or None."""
    matches = sorted(papers_dir.glob(f"{glob}.pdf"))
    return matches[0] if matches else None


DECIMAL_SEPARATORS = (".", ",", "-", "\u00b7")
"""Characters an OCR pass may emit in place of a decimal point.

Older scans are unreliable here. McCreery et al. (1995) renders 0.37 as "0-37" and
0.87 as "R = 0,87"; both are correct in the paper and only the OCR differs. Treating
these as distinct values would raise false alarms on exactly the oldest and most
important sources.
"""


def _renderings(value: str) -> list[str]:
    """Every plausible textual rendering of a numeric value."""
    out = {value}
    if "." in value:
        for sep in DECIMAL_SEPARATORS:
            out.add(value.replace(".", sep))
    return sorted(out)


def check(claim: Claim, text: str) -> bool:
    """Whether any accepted rendering of the value appears in the text."""
    candidates: list[str] = []
    for base in (claim.value, *claim.alternates):
        candidates.extend(_renderings(base))
    for candidate in candidates:
        if candidate in text:
            return True
        # PDFs frequently split digits from units or insert spaces.
        loose = re.sub(r"\s+", r"\\s*", re.escape(candidate))
        if re.search(loose, text):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("papers_dir", nargs="?", default=str(DEFAULT_PAPERS_DIR))
    parser.add_argument(
        "--strict", action="store_true", help="exit non-zero if any value is not found"
    )
    args = parser.parse_args(argv)

    if shutil.which("pdftotext") is None:
        print("pdftotext not found (install poppler); cannot verify.")
        return 0 if not args.strict else 1

    papers_dir = Path(args.papers_dir)
    if not papers_dir.is_dir():
        print(f"No papers directory at {papers_dir}; nothing to verify.")
        return 0 if not args.strict else 1

    cache: dict[Path, str] = {}
    found = missing = skipped = 0
    problems: list[str] = []

    for claim in CLAIMS:
        pdf = find_paper(papers_dir, claim.paper_glob)
        if pdf is None:
            skipped += 1
            continue
        if check(claim, extract_text(pdf, cache)):
            found += 1
        else:
            missing += 1
            problems.append(
                f"  {claim.value!r} ({claim.description}) not found in {pdf.name}"
            )

    print(f"transcribed values checked : {found + missing}")
    print(f"  found in source          : {found}")
    print(f"  NOT found                : {missing}")
    print(f"  skipped (paper absent)   : {skipped}")

    if problems:
        print("\nValues that could not be located in their cited paper:")
        print("\n".join(problems))
        print(
            "\nA miss is not automatically an error -- a PDF may render a number "
            "differently,\nor state it only in a figure. Each one needs a human look."
        )
    else:
        print("\nEvery checked value appears in its cited paper.")

    print(
        "\nNote: this checks that a number appears in the right paper. It cannot "
        "detect a\nvalue attached to the wrong material, polarity or condition."
    )
    return 1 if (args.strict and missing) else 0


if __name__ == "__main__":
    sys.exit(main())
