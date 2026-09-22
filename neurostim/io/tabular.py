"""CSV and JSON import/export, and batch assessment over parameter sets.

The batch path is the one most likely to be used in anger: you have a table of
electrodes and protocols -- a current sweep, a set of contacts, a comparison of
materials -- and you want one row of safety results per combination.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd

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


def protocol_from_dict(spec: Mapping[str, Any]) -> StimProtocol:
    """Build a :class:`~neurostim.protocol.StimProtocol` from a plain mapping."""
    data = {str(k).strip(): v for k, v in spec.items() if v is not None and v != ""}
    allowed = set(StimProtocol.__dataclass_fields__)
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            f"Unknown protocol field(s) {sorted(unknown)}; expected any of "
            f"{sorted(allowed)}"
        )
    return StimProtocol(**data)


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
    """
    electrode_fields: set[str] = set()
    for cls in _ELECTRODE_TYPES.values():
        electrode_fields |= set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    protocol_fields = set(StimProtocol.__dataclass_fields__)
    control_fields = {"k", "policy", "compliance_V", "label"}

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
            unknown = set(clean) - electrode_fields - protocol_fields - control_fields - {"shape"}
            if unknown:
                raise ValueError(f"unrecognised column(s): {sorted(unknown)}")

            electrode = electrode_from_dict(e_spec)
            protocol = protocol_from_dict(p_spec)
            calc = SafetyCalculator(
                electrode,
                protocol,
                k=float(row_k) if (row_k := clean.get("k", k)) is not None else K_DEFAULT,
                policy=str(clean.get("policy", policy)),  # type: ignore[arg-type]
                compliance_V=clean.get("compliance_V", compliance_V),
            )
            record = {"label": label, **calc.report(), "error": ""}
        except Exception as exc:
            if stop_on_error:
                raise
            record = {"label": label, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        results.append(record)

    return pd.DataFrame(results)


def read_batch_csv(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    """Read a batch specification CSV and assess every row."""
    frame = pd.read_csv(path)
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
    """Serialise a full assessment to JSON, including per-check statuses."""
    assessment = calc.assess()
    payload = {
        "electrode": electrode_to_dict(calc.e),
        "protocol": asdict(calc.p),
        "material": calc.material.key,
        "settings": {
            "shannon_k": calc.k,
            "cic_policy": calc.policy,
            "tissue_conductivity_S_per_m": calc.tissue_conductivity_S_per_m,
            "compliance_V": calc.compliance_V,
        },
        "results": calc.report(),
        # Top-level rather than inside ``results``: ``results`` is ``calc.report()``,
        # whose keys become the columns of a sweep CSV, and a list is not a CSV cell.
        "not_evaluated": [c.name for c in assessment.not_evaluated],
        # Non-empty means ``results.limiting_current_uA`` is null and the protocol is
        # unsafe as a waveform, not at some amplitude (ledger 84).
        "unsafe_at_any_amplitude": [
            c.name for c in assessment.unsafe_at_any_amplitude
        ],
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
    text = json.dumps(payload, indent=indent, default=str)
    if path is not None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text


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
    return pd.DataFrame(rows)
