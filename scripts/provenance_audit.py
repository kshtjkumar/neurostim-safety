"""Report the provenance state of every constant in the package.

Run standalone or from CI::

    python scripts/provenance_audit.py [--strict]

Without ``--strict`` this always exits 0: it is a status report. With ``--strict`` it
exits non-zero when the gaps found differ from ``KNOWN_GAPS`` in either direction: a new
gap fails, and so does a known gap that has been closed but is still listed, so the
baseline can only shrink. CI runs it with ``--strict``.
"""

from __future__ import annotations

import argparse
import sys

from neurostim import REFERENCES, list_materials
from neurostim.models.thermal import BRAIN
from neurostim.models.vta import CurrentDistanceModel

# Gaps with no source to close them, acknowledged rather than hidden (C7.6, user decision
# D1). Each is still printed on every run. Remove a line when its gap is closed; --strict
# fails until you do.
KNOWN_GAPS: tuple[str, ...] = (
    "TIROF: no pulse width recorded for its limit, so its applicability at any given "
    "pulse width is unknown",
    "Ta2O5: no water window on record",
    "SS316LVM: no pulse width recorded for its limit, so its applicability at any given "
    "pulse width is unknown",
)


def audit() -> list[str]:
    """Return one line per outstanding provenance gap."""
    gaps: list[str] = []

    for material in list_materials():
        cic = material.cic
        if not cic.verified:
            gaps.append(f"{material.key}: charge-injection limit not primary-sourced")
        if not cic.peer_reviewed:
            gaps.append(
                f"{material.key}: limit rests on a non-peer-reviewed source "
                f"({cic.reference})"
            )
        if cic.pulse_width_us is None:
            gaps.append(
                f"{material.key}: no pulse width recorded for its limit, so its "
                f"applicability at any given pulse width is unknown"
            )
        if material.water_window is None:
            gaps.append(f"{material.key}: no water window on record")

    if not BRAIN.fully_verified:
        missing = [
            name
            for name in (
                "thermal_conductivity_W_per_mK",
                "density_kg_per_m3",
                "specific_heat_J_per_kgK",
                "perfusion_rate_per_s",
            )
            if name not in BRAIN.verified_fields
        ]
        gaps.append(f"tissue thermal properties unsourced: {', '.join(missing)}")

    if not CurrentDistanceModel().verified:
        gaps.append(
            "current-distance constant k is not confirmed against a primary source"
        )

    for key, ref in sorted(REFERENCES.items()):
        if key == "user_measurement":
            continue
        if ref.source_type in ("standard", "abstract"):
            continue  # ISO standards and meeting abstracts are not assigned DOIs
        if not ref.doi and ref.year > 1990:
            gaps.append(f"{key}: post-1990 reference without a DOI")

    return gaps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when any provenance gap remains",
    )
    args = parser.parse_args(argv)

    with_doi = sum(1 for r in REFERENCES.values() if r.doi)
    materials = list_materials()
    print(f"references         {len(REFERENCES)} ({with_doi} with DOI)")
    print(
        f"materials          {len(materials)} "
        f"({sum(1 for m in materials if m.cic.peer_reviewed)} peer-reviewed, "
        f"{sum(1 for m in materials if m.cic.pulse_width_us is not None)} "
        f"with a stated pulse width)"
    )
    print(f"tissue properties  {'fully sourced' if BRAIN.fully_verified else 'INCOMPLETE'}")

    gaps = audit()
    if gaps:
        print(f"\n{len(gaps)} known provenance gap(s):")
        for gap in gaps:
            print(f"  - {gap}")
    else:
        print("\nNo outstanding provenance gaps.")

    new = [gap for gap in gaps if gap not in KNOWN_GAPS]
    closed = [gap for gap in KNOWN_GAPS if gap not in gaps]
    if args.strict and (new or closed):
        for gap in new:
            print(f"--strict: new gap not in KNOWN_GAPS: {gap}")
        for gap in closed:
            print(f"--strict: closed gap still in KNOWN_GAPS, remove it: {gap}")
        return 1
    print("\nThese are documented limitations (KNOWN_GAPS), not regressions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
