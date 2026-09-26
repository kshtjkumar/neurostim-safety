"""CSV and JSON import/export, and batch assessment over parameter sets.

The batch path is the one most likely to be used in anger: you have a table of
electrodes and protocols -- a current sweep, a set of contacts, a comparison of
materials -- and you want one row of safety results per combination.
"""

from __future__ import annotations

import functools
import json
import math
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .. import __version__
from ..geometry import (
    CylindricalBandElectrode,
    DiscElectrode,
    Electrode,
    HemisphericalElectrode,
    MicrowireElectrode,
    RectangularElectrode,
    RingElectrode,
    SphericalElectrode,
)
from ..protocol import StimProtocol
from ..references import cite
from ..safety import SafetyCalculator
from ..safety.shannon import K_DEFAULT

_ELECTRODE_TYPES: dict[str, type[Electrode]] = {
    "disc": DiscElectrode,
    "ring": RingElectrode,
    "rectangle": RectangularElectrode,
    "band": CylindricalBandElectrode,
    "microwire": MicrowireElectrode,
    "sphere": SphericalElectrode,
    "hemisphere": HemisphericalElectrode,
}

_SHAPE_ALIASES = {
    "discelectrode": "disc",
    "ringelectrode": "ring",
    "annulus": "ring",
    "rectangularelectrode": "rectangle",
    "rect": "rectangle",
    "cylindricalbandelectrode": "band",
    "cylinder": "band",
    "dbs": "band",
    "microwireelectrode": "microwire",
    "wire": "microwire",
    "sphericalelectrode": "sphere",
    "hemisphericalelectrode": "hemisphere",
}


def electrode_from_dict(spec: Mapping[str, Any]) -> Electrode:
    """Build an electrode from a plain mapping.

    The mapping needs a ``shape`` key plus that shape's dimension keys, e.g.
    ``{"shape": "ring", "outer_diameter_um": 330, "inner_diameter_um": 270,
    "material": "Pt"}``. Unknown keys are rejected rather than ignored, so a typo in a
    dimension name fails loudly instead of silently falling back to a default.
    """
    data = {str(k).strip(): v for k, v in spec.items() if v is not None and v != ""}
    shape_raw = str(data.pop("shape", "")).strip().lower()
    shape = _SHAPE_ALIASES.get(shape_raw, shape_raw)
    if shape not in _ELECTRODE_TYPES:
        raise ValueError(
            f"Unknown electrode shape {shape_raw!r}. "
            f"Known shapes: {sorted(_ELECTRODE_TYPES)}"
        )
    cls = _ELECTRODE_TYPES[shape]
    allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            f"Unknown field(s) {sorted(unknown)} for shape {shape!r}; "
            f"expected any of {sorted(allowed)}"
        )
    return cls(**data)


def protocol_from_dict(
    spec: Mapping[str, Any], *, null_reasons: Mapping[str, str] | None = None
) -> StimProtocol:
    """Build a :class:`~neurostim.protocol.StimProtocol` from a plain mapping.

    A ``null`` ``train_duration_s`` is how :func:`report_to_json` writes a continuous train
    (ledger 143). It is read back as ``math.inf`` only when ``null_reasons`` says so, as the
    report's own ``null_reasons`` does: a bare null is refused by name rather than taken to
    mean continuous stimulation, the most severe train there is (ledger 146). Other empty
    fields fall back to their defaults, as before.
    """
    if "train_duration_s" in spec and spec["train_duration_s"] is None:
        if not null_reasons or "protocol.train_duration_s" not in null_reasons:
            raise ValueError(
                "train_duration_s is null: a continuous train is math.inf, and a report "
                "written by report_to_json says so in its null_reasons -- read it with "
                "protocol_from_report, or give the duration"
            )
        spec = {**spec, "train_duration_s": math.inf}
    data = {str(k).strip(): v for k, v in spec.items() if v is not None and v != ""}
    allowed = set(StimProtocol.__dataclass_fields__)
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            f"Unknown protocol field(s) {sorted(unknown)}; expected any of "
            f"{sorted(allowed)}"
        )
    return StimProtocol(**data)


def protocol_from_report(payload: Mapping[str, Any]) -> StimProtocol:
    """The protocol a :func:`report_to_json` payload was assessed with (ledger 146)."""
    return protocol_from_dict(payload["protocol"], null_reasons=payload.get("null_reasons"))


def electrode_to_dict(electrode: Electrode) -> dict[str, Any]:
    """Serialise an electrode back to a mapping accepted by :func:`electrode_from_dict`."""
    name = type(electrode).__name__.lower()
    shape = _SHAPE_ALIASES.get(name, name.replace("electrode", ""))
    out: dict[str, Any] = {"shape": shape}
    if is_dataclass(electrode):
        out.update(asdict(electrode))
    return out


def assess_batch(
    rows: Iterable[Mapping[str, Any]],
    *,
    k: float | None = None,
    policy: str = "conservative",
    compliance_V: float | None = None,
    stop_on_error: bool = False,
) -> pd.DataFrame:
    """Run a full safety assessment for every row and return one result row each.

    Each input row is a flat mapping holding electrode fields, protocol fields, and
    optionally ``k``, ``policy`` or ``compliance_V`` overrides. Rows that fail to build
    are reported in an ``error`` column rather than aborting the batch, unless
    ``stop_on_error`` is set -- a sweep of 200 currents should not be lost because one
    of them was mistyped.

    A counter electrode is given by the same electrode columns prefixed ``counter_``
    (``counter_shape``, ``counter_diameter_um``, ``counter_material``, ...) plus
    ``counter_separation_um``; blank cells mean none (ledger 126).

    A failed row has status ``"ERROR"`` and ``None`` in every result column, and the batch
    emits :class:`BatchRowsFailedWarning` naming how many failed; their labels are in
    ``frame.attrs["rows_failed"]``. pandas skips missing values when it aggregates, so
    ``frame.limiting_current_uA.min()`` over a batch with failed rows is the minimum over
    the rows that ran -- exclude or fix the failed ones first (ledger 61/M4). No rows at
    all returns an empty frame that still has every column (ledger 51).
    """
    electrode_fields: set[str] = set()
    for cls in _ELECTRODE_TYPES.values():
        electrode_fields |= set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    protocol_fields = set(StimProtocol.__dataclass_fields__)
    control_fields = {"k", "policy", "compliance_V", "label", "counter_separation_um"}
    counter_fields = {f"counter_{field}" for field in electrode_fields | {"shape"}}

    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        clean = {str(key).strip(): value for key, value in row.items()}
        label = clean.get("label", index)
        try:
            e_spec = {
                key: value
                for key, value in clean.items()
                if key in electrode_fields or key == "shape"
            }
            p_spec = {
                key: value
                for key, value in clean.items()
                if key in protocol_fields and key not in electrode_fields
            }
            unknown = (
                set(clean)
                - electrode_fields
                - protocol_fields
                - control_fields
                - counter_fields
                - {"shape"}
            )
            if unknown:
                raise ValueError(f"unrecognised column(s): {sorted(unknown)}")

            electrode = electrode_from_dict(e_spec)
            protocol = protocol_from_dict(p_spec)
            # A counter electrode is the counter_-prefixed electrode columns, plus its
            # centre-to-centre separation; blank cells mean none (ledger 126).
            c_spec = {
                key[len("counter_"):]: value
                for key, value in clean.items()
                if key in counter_fields and not _blank(value)
            }
            separation = clean.get("counter_separation_um")
            calc = SafetyCalculator(
                electrode,
                protocol,
                k=float(row_k) if (row_k := clean.get("k", k)) is not None else K_DEFAULT,
                policy=str(clean.get("policy", policy)),  # type: ignore[arg-type]
                compliance_V=clean.get("compliance_V", compliance_V),
                counter_electrode=electrode_from_dict(c_spec) if c_spec else None,
                counter_separation_um=(
                    None if separation is None or _blank(separation) else float(separation)
                ),
            )
            record = {"label": label, **calc.report(), "error": ""}
        except Exception as exc:
            if stop_on_error:
                raise
            record = {"label": label, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        results.append(record)

    columns = ["label", *_result_columns(), "error"]
    failed = [record["label"] for record in results if record["status"] == "ERROR"]
    # With a failed row every column is built as the nullable ones are, so the failed row
    # reads None, not NaN, in each result it does not have.
    frame = _frame(results, columns, nullable=columns if failed else NULLABLE_COLUMNS)
    frame.attrs["rows_failed"] = failed
    if failed:
        warnings.warn(
            f"{len(failed)} of {len(results)} rows failed to build (labels {failed}); they "
            f"carry status 'ERROR' and no results, so exclude them before aggregating, or "
            f"pass stop_on_error=True",
            BatchRowsFailedWarning,
            stacklevel=2,
        )
    return frame


def _blank(value: Any) -> bool:
    """An absent cell: ``None``, or the NaN pandas reads for an empty CSV cell."""
    return value is None or (isinstance(value, float) and math.isnan(value))


class BatchRowsFailedWarning(UserWarning):
    """Some rows of a batch failed to build and carry no results (ledger 61/M4)."""


@functools.cache
def _result_columns() -> tuple[str, ...]:
    """The keys :meth:`SafetyCalculator.report` returns, in its order.

    Read off one assessment rather than listed, so a key added to ``report()`` is a column
    of every batch, failed rows included, the day it is added.
    """
    from ..geometry.planar import DiscElectrode

    sample = SafetyCalculator(DiscElectrode(200.0, "Pt"), StimProtocol(50.0, 200.0, 130.0, 1.0))
    return tuple(sample.report())


NULLABLE_COLUMNS = (
    "limiting_current_uA",
    "required_compliance_V",
    "limit_is_provisional",
    "max_current_cic_uA",
    "cic_limit_uC_cm2",
)
"""Result columns that are ``None`` where no number exists (ledgers 84, 143, 147), where
there is no limit for a flag to qualify (ledger 158), or where the check that would give
the number did not run (ledger 114)."""


def _frame(
    records: list[dict[str, Any]],
    columns: list[str] | None = None,
    nullable: Iterable[str] = NULLABLE_COLUMNS,
) -> pd.DataFrame:
    """A results frame whose nullable columns hold ``None``, never ``NaN``.

    pandas turns ``None`` into ``NaN`` in a column that also holds numbers, and keeps it as
    ``None`` in one that does not, so the same row read differently depending on the rest
    of the batch (ledger 147). ``report()`` and the JSON say ``None``, so the frame does too:
    those columns are object dtype, a float or ``None`` in every row. On disk both are an
    empty CSV cell, as before.
    """
    frame = pd.DataFrame(records, columns=columns)
    for column in nullable:
        if column in frame and len(frame):
            frame[column] = pd.Series(
                [record.get(column) for record in records], index=frame.index, dtype=object
            )
    return frame


def read_batch_csv(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    """Read a batch specification CSV and assess every row.

    A file that cannot be parsed, or holds no rows to assess, raises ``ValueError`` naming
    the file: pandas' own errors gave a byte offset or "No columns to parse" and no path,
    which in a batch of many files identifies nothing (ledger 61/M14), and a header-only
    file used to come back as an empty frame, indistinguishable from a clean one
    (ledger 51).
    """
    try:
        frame = pd.read_csv(path)
    except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"cannot read batch CSV {path}: {type(exc).__name__}: {exc}") from exc
    if frame.empty:
        raise ValueError(f"batch CSV {path} has no rows to assess (header only)")
    return assess_batch(frame.to_dict(orient="records"), **kwargs)


def write_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write a results table to CSV."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    return out


def report_to_json(
    calc: SafetyCalculator, path: str | Path | None = None, *, indent: int = 2
) -> str:
    """Serialise a full assessment to JSON, including per-check statuses.

    Strict JSON (RFC 8259): no ``Infinity`` or ``NaN`` is ever emitted (ledger 143). A
    quantity that is unbounded is written as ``null``, and ``null_reasons`` maps its path
    to a sentence saying why:

    - ``protocol.train_duration_s`` is ``null`` for continuous stimulation;
    - ``results.required_compliance_V`` is ``null`` when no finite voltage suffices (a
      continuous unbalanced train with an uncapped offset), and the same sentence is in
      ``results.required_compliance_note``.

    A path absent from ``null_reasons`` is a real number wherever it is not ``null`` for
    the reasons documented beside its key. Serialised with ``allow_nan=False``, so a new
    non-finite field raises here instead of producing invalid JSON.
    """
    assessment = calc.assess()
    protocol = asdict(calc.p)
    results = calc.report()
    null_reasons: dict[str, str] = {}
    if math.isinf(calc.p.train_duration_s):
        protocol["train_duration_s"] = None
        null_reasons["protocol.train_duration_s"] = "continuous stimulation: the train has no end"
    if results["required_compliance_V"] is None:
        null_reasons["results.required_compliance_V"] = results["required_compliance_note"]
    if results["max_current_cic_uA"] is None:
        cic = next(c for c in assessment.checks if c.name == "Charge injection limit")
        reason = f"Charge injection limit not evaluated: {cic.summary}"
        null_reasons["results.max_current_cic_uA"] = reason
        null_reasons["results.cic_limit_uC_cm2"] = reason
    payload = {
        "electrode": electrode_to_dict(calc.e),
        "protocol": protocol,
        "material": calc.material.key,
        "package_version": __version__,
        # Every calculator setting, the counter included (ledgers 59, 126). It used to
        # carry 4 of 11, so two assessments that differed in, say, the resting potential
        # serialised the same settings beside different results.
        "settings": calculator_settings(calc, counter_always=True),
        "results": results,
        "null_reasons": null_reasons,
        "provenance": _provenance(calc.material),
        # Top-level rather than inside ``results``: ``results`` is ``calc.report()``,
        # whose keys become the columns of a sweep CSV, and a list is not a CSV cell.
        "not_evaluated": [c.name for c in assessment.not_evaluated],
        # Non-empty means ``results.limiting_current_uA`` is null and the protocol is
        # unsafe as a waveform, not at some amplitude (ledger 84).
        "unsafe_at_any_amplitude": [
            c.name for c in assessment.unsafe_at_any_amplitude
        ],
        # The other way ``results.limiting_current_uA`` is null: a limit-bearing check
        # whose ceiling has closed to zero, so it permits no current at all under the
        # settings given. A separate key from the one above because the two carry
        # different instructions -- change the waveform, or change the setting that closed
        # the limit (ledger 99).
        "permits_no_current": [c.name for c in assessment.permits_no_current],
        # True means the limit was computed over a candidate set known to be missing a
        # member, so the true limit may be lower than ``results.limiting_current_uA``.
        "limits_incomplete": assessment.limits_incomplete,
        # True means the limit is inherited from the biphasic counterpart rather than set
        # by one of this protocol's own checks: a monophasic waveform is strictly worse
        # and cannot earn a higher limit than the biphasic one (ledger 2).
        "monotonicity_capped": assessment.monotonicity_capped,
        "limiting_current_by_kind": {
            kind: None if value == float("inf") else value
            for kind, value in assessment.limiting_current_by_kind.items()
        },
        "checks": [
            {
                "name": c.name,
                "status": c.status.value,
                "kind": c.kind,
                "summary": c.summary,
                "margin": None if c.margin == float("inf") else c.margin,
                "ceiling_uA": None if c.ceiling_uA == float("inf") else c.ceiling_uA,
                "provisional": c.provisional,
            }
            for c in assessment.checks
        ],
        "disclaimer": (
            "Not validated for clinical or regulatory use. Limits are empirical or "
            "modelled estimates."
        ),
    }
    text = json.dumps(payload, indent=indent, default=str, allow_nan=False)
    if path is not None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text


def calculator_settings(calc: SafetyCalculator, *, counter_always: bool) -> dict[str, Any]:
    """Every setting a :class:`SafetyCalculator` was built with, under its record key.

    One builder for the JSON report, the audit record and the PDF, so the three cannot
    disagree about what was set. ``counter_always`` writes ``counter_electrode`` and
    ``counter_separation_um`` as ``None`` when no counter is supplied (the JSON). The audit
    record leaves them out then, so the digest of a record made without a counter is what
    it was before the counter keys existed.
    """
    settings: dict[str, Any] = {
        "shannon_k": calc.k,
        "cic_policy": calc.policy,
        "medium": calc.medium,
        "tissue_conductivity_S_per_m": calc.tissue_conductivity_S_per_m,
        "lead_resistance_ohm": calc.lead_resistance_ohm,
        "compliance_V": calc.compliance_V,
        "measured_impedance_ohm": calc.measured_impedance_ohm,
        "resting_potential_V": calc.resting_potential_V,
        "capacitance_uF_cm2": calc.capacitance_uF_cm2,
    }
    if counter_always or calc.counter_electrode is not None:
        settings["counter_electrode"] = (
            electrode_to_dict(calc.counter_electrode)
            if calc.counter_electrode is not None
            else None
        )
        settings["counter_separation_um"] = calc.counter_separation_um
    return settings


def _provenance(material: Any) -> dict[str, Any]:
    """Each applied constant's reference key and verified flag, and the roll-up (ledger 30).

    ``None`` for a constant the material does not carry.
    """

    def entry(constant: Any) -> dict[str, Any] | None:
        if constant is None:
            return None
        return {
            "reference": constant.reference,
            "verified": constant.verified,
            # The material the value was published for, when a user material carries it
            # over; null for a value published for this material (ledger 25).
            "inherited_from": getattr(constant, "inherited_from", "") or None,
            # The flags the PDF shows and the JSON did not (ledger 59): whether the source
            # went through peer review, and the note stored with the value -- for a user
            # measurement, the user's own.
            "peer_reviewed": cite(constant.reference).peer_reviewed,
            "note": constant.note,
        }

    return {
        "material_verified": material.verified,
        "dropped": list(material.dropped),
        "cic": entry(material.cic),
        "water_window": entry(material.water_window),
        "chronic_threshold": entry(material.chronic_threshold),
    }


def current_sweep(
    electrode: Electrode,
    base_protocol: StimProtocol,
    currents_uA: Iterable[float],
    **calculator_kwargs: Any,
) -> pd.DataFrame:
    """Assess one electrode over a range of currents.

    The common case for choosing a working amplitude: everything else is held fixed and
    the binding limit is read off the ``limiting_current_uA`` column.
    """
    from dataclasses import replace

    rows = []
    for current in currents_uA:
        protocol = replace(base_protocol, current_uA=float(current))
        calc = SafetyCalculator(electrode, protocol, **calculator_kwargs)
        rows.append({"current_uA": float(current), **calc.report()})
    return _frame(rows)
