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

Until payload version 3 it did exactly that for everything outside the material record:
a record of a 500 um Pt disc in vivo, made before the in-vivo derating moved, still
"reproduced" when its limiting current had gone from 70.12 to 112.84 uA (ledger 155).
Version 3 adds the answer itself -- the limiting current and mechanism, the status, the
flags, and every check's status, ceiling and provisional flag -- and a SHA-256 of the
module-level constants of every module the assessment reads (:data:`MODEL_CONSTANT_MODULES`),
one hash per module so a mismatch names the module.

What reproduces means
---------------------
:func:`reproduces` rebuilds the record at the original's payload version and compares it
section by section, and compares the stored ``results`` with fresh ones key by key,
whatever the version -- so a version 1 or 2 record whose answer moved fails too, and
says which value moved. The package version is recorded and reported, but a difference
in it alone is not a failure: when the inputs, the constants, the model constants and the
answer all agree, the result has been reproduced, whichever release computed it.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import importlib
import json
import math
import platform
from dataclasses import asdict, dataclass, field
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
    payload_version: int = 1
    """Which payload the digest is taken over (ledger 77, S-10).

    1 is the payload before the measurement conditions joined it; a record loaded without
    this field is version 1, and keeps computing and verifying the old way. 2 adds
    :attr:`constants_v2`. :func:`record` writes version 2."""
    constants_v2: dict[str, Any] = field(default_factory=dict)
    """The conditions the version 1 digest left out: the verified flag, area basis,
    waveform, bias, medium, temperature, measured area, polarity sub-ranges and the
    recommended policy -- the conditions the package says are its point."""
    answer: dict[str, Any] = field(default_factory=dict)
    """Version 3: the answer the digest certifies (ledger 155); see :func:`answer_of`."""
    model_constants: dict[str, str] = field(default_factory=dict)
    """Version 3: one SHA-256 per module in :data:`MODEL_CONSTANT_MODULES`; see
    :func:`model_constants`."""

    def payload(self) -> dict[str, Any]:
        """The parts of the record the digest is taken over.

        Excludes the timestamp, operator and note: the same calculation run twice by
        different people on different days must produce the same digest.
        """
        body: dict[str, Any] = {
            "package_version": self.package_version,
            "electrode": self.electrode,
            "protocol": self.protocol,
            "settings": self.settings,
            "constants": self.constants,
        }
        if self.payload_version >= 2:
            body["payload_version"] = self.payload_version
            body["constants_v2"] = self.constants_v2
        if self.payload_version >= 3:
            body["answer"] = self.answer
            body["model_constants"] = self.model_constants
        return body

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
        """Every payload field that differs, as ``"path: this -> other"``.

        Use when a digest fails to match: this says which input or constant moved. Nested
        sections are walked to the leaf, so a moved check ceiling reads
        ``answer.checks.<name>.ceiling_uA``, not the whole table.
        """
        return _diff("", self.payload(), other.payload())


def _diff(path: str, a: Any, b: Any) -> list[str]:
    """Leaf-level differences between two JSON-shaped values."""
    if a == b:
        return []
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b), key=str):
            out += _diff(f"{path}.{key}" if path else str(key), a.get(key), b.get(key))
        return out
    return [f"{path}: {a!r} -> {b!r}"]


PAYLOAD_VERSION = 4
"""The payload :func:`record` writes (ledger 77, S-10; version 3, ledger 155; version 4,
ledger 160)."""

MODEL_CONSTANT_MODULES: tuple[str, ...] = (
    "neurostim.data.butterwick2007",
    "neurostim.data.cogan2016",
    "neurostim.data.gabriel1996",
    "neurostim.data.mccreery1995",
    "neurostim.data.mccreery2010",
    "neurostim.geometry.arrays",
    "neurostim.geometry.base",
    "neurostim.geometry.planar",
    "neurostim.geometry.volumetric",
    "neurostim.materials",
    "neurostim.protocol",
    "neurostim.safety._limits",
    "neurostim.safety.assessment",
    "neurostim.safety.charge",
    "neurostim.safety.compliance",
    "neurostim.safety.current_density",
    "neurostim.safety.envelope",
    "neurostim.safety.shannon",
    "neurostim.safety.water_window",
    "neurostim.uncertainty",
    "neurostim.units",
)
"""Every module whose module-level constants the assessment reads (ledger 155).

The data modules are the ones :mod:`neurostim.safety` imports; a test holds the list to
that. A constant is a module attribute named in capitals (``_CAPITALS`` included) that
is not a module, class or function."""


def _canonical(value: Any) -> Any:
    """A JSON-shaped, deterministic form of one constant.

    Floats go through ``repr``, which round-trips exactly and names ``inf``; dataclasses
    by field; mappings by sorted key; functions by qualified name; a sentinel with no
    state by its class. Anything else raises rather than hashing something unstable.
    """
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, enum.Enum):
        return _canonical(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _canonical(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]
    if isinstance(value, set | frozenset):
        return sorted((_canonical(v) for v in value), key=repr)
    if callable(value):
        return f"{value.__module__}.{value.__qualname__}"
    if not getattr(value, "__dict__", None) and not getattr(type(value), "__slots__", ()):
        return f"<{type(value).__module__}.{type(value).__qualname__}>"
    raise TypeError(f"cannot canonicalise a model constant of type {type(value).__name__}")


def _is_constant_name(name: str) -> bool:
    bare = name.lstrip("_")
    return bool(bare) and bare.upper() == bare and any(c.isalpha() for c in bare)


def model_constants() -> dict[str, str]:
    """One SHA-256 per module in :data:`MODEL_CONSTANT_MODULES`, over its constants."""
    import types

    hashes: dict[str, str] = {}
    for name in MODEL_CONSTANT_MODULES:
        module = importlib.import_module(name)
        constants = {
            key: _canonical(value)
            for key, value in sorted(vars(module).items())
            if _is_constant_name(key)
            and not isinstance(value, types.ModuleType | type)
            and not (callable(value) and not isinstance(value, dict))
        }
        canonical = json.dumps(constants, sort_keys=True, separators=(",", ":"))
        hashes[name] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return hashes


def _finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None


def answer_of(calc: SafetyCalculator, payload_version: int = PAYLOAD_VERSION) -> dict[str, Any]:
    """The answer a version 3 or 4 digest certifies (ledgers 155, 160).

    The limiting current and mechanism, the overall status, the three flags that qualify
    the limit, and every check's status, ceiling and provisional flag. Version 4 adds the
    limiting current interval over the published ranges and the limit within each check
    kind: function bodies are not hashed, so a code change in a band provider moved the
    interval with a version 3 record still reproducing (ledger 160). An unbounded value is
    ``None``, as in the strict JSON report.
    """
    assessment = calc.assess()
    report = calc.report()
    answer = {
        "limiting_current_uA": report["limiting_current_uA"],
        "limiting_mechanism": report["limiting_mechanism"],
        "status": report["status"],
        "limit_is_provisional": assessment.limit_is_provisional,
        "limits_incomplete": assessment.limits_incomplete,
        "unsafe_at_any_amplitude": [c.name for c in assessment.unsafe_at_any_amplitude],
        "checks": {
            check.name: {
                "status": check.status.value,
                "ceiling_uA": _finite_or_none(check.ceiling_uA),
                "provisional": check.provisional,
            }
            for check in assessment.checks
        },
    }
    if payload_version >= 4:
        interval = assessment.limiting_current_interval_uA
        answer["limiting_current_interval_uA"] = [
            _finite_or_none(interval.low),
            _finite_or_none(interval.high),
        ]
        answer["limiting_current_by_kind"] = {
            kind: _finite_or_none(value)
            for kind, value in assessment.limiting_current_by_kind.items()
        }
    return answer


def record(
    calc: SafetyCalculator,
    *,
    operator: str = "",
    note: str = "",
    payload_version: int = PAYLOAD_VERSION,
) -> AuditRecord:
    """Build a reproducibility record for a calculator's current configuration.

    ``payload_version=1`` builds the record as it was before the conditions joined the
    digest, which is what :func:`reproduces` does to check a version 1 record.
    """
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

    cic = material.cic
    constants_v2: dict[str, Any] = {}
    if payload_version >= 2:
        constants_v2 = {
            "cic_verified": cic.verified,
            "cic_area_basis": cic.area_basis,
            "cic_waveform": cic.waveform,
            "cic_bias": cic.bias,
            "cic_medium": cic.medium,
            "cic_temperature_C": cic.temperature_C,
            "cic_measured_area_cm2": cic.measured_area_cm2,
            "cic_anodic_first_range": (
                list(cic.anodic_first_range) if cic.anodic_first_range else None
            ),
            "cic_cathodic_first_range": (
                list(cic.cathodic_first_range) if cic.cathodic_first_range else None
            ),
            "cic_recommended_policy": cic.recommended_policy,
        }
    answer: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    if payload_version >= 3:
        answer = answer_of(calc, payload_version)
        hashes = model_constants()
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
        payload_version=payload_version,
        constants_v2=constants_v2,
        answer=answer,
        model_constants=hashes,
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
    versions. The differences read ``"path: recorded -> now"``. The stored results are
    compared key by key at every payload version, so an old record whose answer moved
    fails and names the value (ledger 155); a key only one side has is not compared. A
    package-version difference is listed beside a failure but is not one by itself; see
    the module docstring.

    What a record can check is what it stored. Version 1 and 2 records compare only their
    stored ``report()`` keys, so they cannot see a change confined to a single check's
    status or ceiling -- a Water window going PASS to CAUTION while the headline holds
    reproduces for them. Version 3 records see every check; version 4 records also see the
    interval over the published ranges and the limit per check kind (ledgers 160, 161).
    """
    # At the stored record's own payload version, so a version 1 record is checked the way
    # it was made (ledger 77, S-10).
    fresh = record(calc, payload_version=original.payload_version)
    diffs = original.differences_from(fresh)
    shared = sorted(set(original.results) & set(fresh.results))
    diffs += _diff(
        "results",
        {key: original.results[key] for key in shared},
        {key: fresh.results[key] for key in shared},
    )
    failing = [d for d in diffs if not d.startswith("package_version:")]
    if not failing:
        return True, []
    return False, diffs
