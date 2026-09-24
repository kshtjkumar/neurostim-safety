"""Reproducibility record for an assessment.

A safety number quoted in a methods section or a lab notebook is only useful if someone
can later establish what produced it. Package versions move, constants get corrected --
this package corrected four of its own during development -- and a figure with no
provenance becomes unfalsifiable.

An :class:`AuditRecord` captures everything needed to reproduce or refute a result: the
package version, the full input set, the constants that were in force, and a digest over
all of it. Two records with the same digest were computed identically; two that differ
can be diffed to find out why.

What the digest covers
----------------------
Inputs *and* the constants they were evaluated against. If a charge-injection limit is
later corrected, an old record's digest will no longer match a fresh run of the same
inputs -- which is the point. A digest over inputs alone would silently claim
reproducibility across a change that altered the answer.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .safety.assessment import SafetyCalculator


@dataclass(frozen=True)
class AuditRecord:
    """Everything needed to reproduce one assessment."""

    package_version: str
    timestamp_utc: str
    python_version: str
    electrode: dict[str, Any]
    protocol: dict[str, Any]
    settings: dict[str, Any]
    constants: dict[str, Any]
    results: dict[str, Any]
    digest: str = ""
    note: str = ""
    operator: str = ""

    def payload(self) -> dict[str, Any]:
        """The parts of the record the digest is taken over.

        Excludes the timestamp, operator and note: the same calculation run twice by
        different people on different days must produce the same digest.
        """
        return {
            "package_version": self.package_version,
            "electrode": self.electrode,
            "protocol": self.protocol,
            "settings": self.settings,
            "constants": self.constants,
        }

    def compute_digest(self) -> str:
        """SHA-256 over the canonicalised payload."""
        canonical = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def digest_matches(self) -> bool:
        """Whether the stored digest still describes the stored payload."""
        return self.digest == self.compute_digest()

    def to_json(self, indent: int = 2) -> str:
        """Serialise the whole record as strict JSON (ledger 149).

        A continuous train's duration is written as ``null``, with its reason in
        ``null_reasons``, as :func:`neurostim.io.tabular.report_to_json` does; it used to be
        ``Infinity``, which is not JSON. :func:`load` restores it. The digest is untouched:
        it is computed over the record held in memory, with the duration still ``inf``, so a
        stored digest reproduces across the change.
        """
        body = asdict(self)
        null_reasons: dict[str, str] = {}
        duration = body["protocol"].get("train_duration_s")
        if isinstance(duration, float) and math.isinf(duration):
            body["protocol"] = {**body["protocol"], "train_duration_s": None}
            null_reasons["protocol.train_duration_s"] = (
                "continuous stimulation: the train has no end"
            )
        body["null_reasons"] = null_reasons
        return json.dumps(body, indent=indent, default=str, allow_nan=False)

    def describe(self) -> str:
        """Short human-readable header."""
        lines = [
            f"neurostim {self.package_version} on Python {self.python_version}",
            f"recorded {self.timestamp_utc}",
            f"digest   {self.digest[:16]}...",
        ]
        if self.operator:
            lines.append(f"operator {self.operator}")
        if self.note:
            lines.append(f"note     {self.note}")
        return "\n".join(lines)

    def differences_from(self, other: AuditRecord) -> list[str]:
        """Every payload field that differs between two records.

        Use when a digest fails to match: this says which input or constant moved.
        """
        diffs: list[str] = []
        mine, theirs = self.payload(), other.payload()
        for section in sorted(set(mine) | set(theirs)):
            a, b = mine.get(section), theirs.get(section)
            if a == b:
                continue
            if isinstance(a, dict) and isinstance(b, dict):
                for key in sorted(set(a) | set(b)):
                    if a.get(key) != b.get(key):
                        diffs.append(f"{section}.{key}: {a.get(key)!r} -> {b.get(key)!r}")
            else:
                diffs.append(f"{section}: {a!r} -> {b!r}")
        return diffs


def record(
    calc: SafetyCalculator, *, operator: str = "", note: str = ""
) -> AuditRecord:
    """Build a reproducibility record for a calculator's current configuration."""
    # Imported here rather than at module scope: the package __init__ imports this
    # module, so a top-level import of __version__ would be circular.
    from . import __version__
    from .io.tabular import calculator_settings, electrode_to_dict

    material = calc.material
    constants: dict[str, Any] = {
        "material": material.key,
        "cic_units": material.cic.units,
        "cic_low": material.cic.low,
        "cic_high": material.cic.high,
        "cic_reference": material.cic.reference,
        "cic_pulse_width_us": material.cic.pulse_width_us,
        "shannon_k_default": calc.k,
    }
    if material.water_window is not None:
        constants["water_window_V"] = [
            material.water_window.cathodic_V,
            material.water_window.anodic_V,
        ]
    if material.chronic_threshold is not None:
        constants["chronic_threshold_uC_cm2"] = [
            material.chronic_threshold.low_uC_cm2,
            material.chronic_threshold.high_uC_cm2,
        ]

    rec = AuditRecord(
        package_version=__version__,
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        python_version=platform.python_version(),
        electrode=electrode_to_dict(calc.e),
        protocol=asdict(calc.p),
        # The counter enters only when there is one (ledger 126), so a record made
        # without a counter keeps the settings, and the digest, it always had.
        settings=calculator_settings(calc, counter_always=False),
        constants=constants,
        results=calc.report(),
        operator=operator,
        note=note,
    )
    # Frozen dataclass: rebuild with the digest filled in.
    return AuditRecord(**{**asdict(rec), "digest": rec.compute_digest()})


def load(text: str) -> AuditRecord:
    """Rebuild a record from its JSON form, strict or written before ledger 149.

    A ``null`` duration explained in ``null_reasons`` is a continuous train and becomes
    ``inf`` again, so the digest is recomputed over what it was computed over.
    """
    body = json.loads(text)
    null_reasons = body.pop("null_reasons", {}) or {}
    if (
        body.get("protocol", {}).get("train_duration_s") is None
        and "protocol.train_duration_s" in null_reasons
    ):
        body["protocol"] = {**body["protocol"], "train_duration_s": math.inf}
    return AuditRecord(**body)


def reproduces(original: AuditRecord, calc: SafetyCalculator) -> tuple[bool, list[str]]:
    """Whether a calculator reproduces a stored record, and what differs if not.

    The usual failure is not a mistake but a correction: a constant moved between
    versions. The returned differences say which.
    """
    fresh = record(calc)
    if fresh.digest == original.digest:
        return True, []
    return False, fresh.differences_from(original)
