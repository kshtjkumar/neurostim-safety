"""Import hooks for externally computed finite element field solutions.

Why this exists
---------------
The analytic field model in :mod:`neurostim.models.field` assumes a homogeneous,
isotropic, unbounded medium and a spherical source. Real answers about field
distribution around a real electrode in real tissue come from a finite element solve
that respects the actual geometry, the encapsulation layer, and white-matter anisotropy.
This module does not perform that solve; it brings the result of one back in so the rest
of the package can use it.

Supported input
---------------
A scattered-point field export: a table of ``x, y, z, V`` (positions in micrometres,
potential in volts). Every major solver can produce this --- COMSOL via *Export > Data*
on a cut point/volume dataset, Sim4Life via a field-to-CSV export, and any VTK-based
pipeline via ``numpy`` on the point data. CSV, TSV and ``.npz`` are read directly.

Deliberately not implemented: parsing solver-native binary formats. Those are versioned,
undocumented, and would fail silently against the wrong release. A CSV export is one
click away and cannot be misread.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_POSITION_ALIASES = {
    "x": ("x", "x_um", "x [um]", "x (um)", "coord_x", "% x"),
    "y": ("y", "y_um", "y [um]", "y (um)", "coord_y"),
    "z": ("z", "z_um", "z [um]", "z (um)", "coord_z"),
}
_POTENTIAL_ALIASES = ("v", "v_v", "potential", "potential_v", "phi", "voltage", "es.v")


def _match_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {c.strip().lower(): c for c in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


@dataclass
class FEMField:
    """A scattered-point potential field imported from an external solver."""

    points_um: np.ndarray
    potential_V: np.ndarray
    source: str = ""
    current_uA: float | None = None
    note: str = ""

    def __post_init__(self) -> None:
        self.points_um = np.asarray(self.points_um, dtype=float)
        self.potential_V = np.asarray(self.potential_V, dtype=float)
        if self.points_um.ndim != 2 or self.points_um.shape[1] != 3:
            raise ValueError(
                f"points_um must have shape (n, 3), got {self.points_um.shape}"
            )
        if self.potential_V.shape != (self.points_um.shape[0],):
            raise ValueError(
                f"potential_V must have one value per point: expected "
                f"{(self.points_um.shape[0],)}, got {self.potential_V.shape}"
            )
        if self.points_um.shape[0] < 4:
            raise ValueError(
                f"need at least 4 points to interpolate a 3-D field, "
                f"got {self.points_um.shape[0]}"
            )

    @property
    def n_points(self) -> int:
        """Number of sample points."""
        return int(self.points_um.shape[0])

    @property
    def bounds_um(self) -> tuple[np.ndarray, np.ndarray]:
        """Axis-aligned bounding box of the sampled region."""
        return self.points_um.min(axis=0), self.points_um.max(axis=0)

    def interpolate_V(
        self, query_points_um: np.ndarray, *, method: str = "linear"
    ) -> np.ndarray:
        """Interpolate the potential at arbitrary points.

        Points outside the convex hull of the imported data return ``nan`` rather than
        an extrapolated value: extrapolating a field solution beyond its domain produces
        numbers that look plausible and are not.
        """
        from scipy.interpolate import griddata

        query = np.asarray(query_points_um, dtype=float)
        if query.ndim != 2 or query.shape[1] != 3:
            raise ValueError(f"query_points_um must have shape (n, 3), got {query.shape}")
        return griddata(self.points_um, self.potential_V, query, method=method)

    def scale_to_current(self, current_uA: float) -> FEMField:
        """Linearly rescale the field to a different stimulation current.

        Valid because the quasi-static conduction problem is linear in the source
        current. Requires the imported field to record the current it was solved at.
        """
        if self.current_uA is None:
            raise ValueError(
                "this field has no current_uA on record, so it cannot be rescaled; "
                "set FEMField.current_uA to the value the solve used"
            )
        if not math.isfinite(current_uA):
            raise ValueError(f"current_uA must be finite, got {current_uA!r}")
        factor = current_uA / self.current_uA
        return FEMField(
            points_um=self.points_um.copy(),
            potential_V=self.potential_V * factor,
            source=self.source,
            current_uA=current_uA,
            note=f"rescaled from {self.current_uA:g} uA by {factor:g}",
        )

    def gradient_magnitude_V_per_m(
        self, query_points_um: np.ndarray, *, step_um: float = 1.0
    ) -> np.ndarray:
        """Electric field magnitude by central differences on the interpolant.

        ``step_um`` must be large enough to span several sample spacings, or the
        difference will be dominated by interpolation noise rather than by the field.
        """
        query = np.asarray(query_points_um, dtype=float)
        grads = np.zeros((query.shape[0], 3))
        for axis in range(3):
            offset = np.zeros(3)
            offset[axis] = step_um
            forward = self.interpolate_V(query + offset)
            backward = self.interpolate_V(query - offset)
            grads[:, axis] = (forward - backward) / (2.0 * step_um * 1e-6)
        return np.linalg.norm(grads, axis=1)

    def describe(self) -> str:
        """Multi-line summary."""
        lo, hi = self.bounds_um
        lines = [
            f"FEM field: {self.n_points} points from {self.source or 'unknown source'}",
            f"  bounds x [{lo[0]:g}, {hi[0]:g}] um, "
            f"y [{lo[1]:g}, {hi[1]:g}] um, z [{lo[2]:g}, {hi[2]:g}] um",
            f"  potential {self.potential_V.min():.4g} to "
            f"{self.potential_V.max():.4g} V",
        ]
        if self.current_uA is not None:
            lines.append(f"  solved at {self.current_uA:g} uA")
        if self.note:
            lines.append(f"  {self.note}")
        return "\n".join(lines)


def load_field(
    path: str | Path,
    *,
    current_uA: float | None = None,
    position_scale_to_um: float = 1.0,
    **read_kwargs,
) -> FEMField:
    """Load a scattered-point field export.

    Parameters
    ----------
    position_scale_to_um:
        Multiplier converting the file's length unit to micrometres. COMSOL commonly
        exports in metres, in which case pass ``1e6``. Getting this wrong is the most
        likely import error, so the resulting bounds are worth checking against the
        geometry you modelled -- :meth:`FEMField.describe` prints them.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No such field export: {p}")

    if p.suffix.lower() == ".npz":
        with np.load(p) as data:
            keys = set(data.files)
            if {"points_um", "potential_V"} <= keys:
                points = data["points_um"]
                potential = data["potential_V"]
            elif {"x", "y", "z", "v"} <= {k.lower() for k in keys}:
                lookup = {k.lower(): k for k in keys}
                points = np.column_stack(
                    [data[lookup["x"]], data[lookup["y"]], data[lookup["z"]]]
                )
                potential = data[lookup["v"]]
            else:
                raise ValueError(
                    f"{p.name} must contain either 'points_um' and 'potential_V', or "
                    f"'x', 'y', 'z' and 'v'; found {sorted(keys)}"
                )
    else:
        sep = read_kwargs.pop("sep", "\t" if p.suffix.lower() in (".tsv", ".txt") else ",")
        frame = pd.read_csv(p, sep=sep, comment="%", **read_kwargs)
        columns = list(frame.columns)
        resolved = {
            axis: _match_column(columns, aliases)
            for axis, aliases in _POSITION_ALIASES.items()
        }
        v_col = _match_column(columns, _POTENTIAL_ALIASES)
        missing = [a for a, c in resolved.items() if c is None]
        if missing or v_col is None:
            wanted = missing + ([] if v_col else ["potential"])
            raise ValueError(
                f"Could not find column(s) for {wanted} in {p.name}. "
                f"Columns present: {columns}"
            )
        points = frame[[resolved["x"], resolved["y"], resolved["z"]]].to_numpy(float)
        potential = frame[v_col].to_numpy(float)

    return FEMField(
        points_um=np.asarray(points, dtype=float) * position_scale_to_um,
        potential_V=potential,
        source=str(p),
        current_uA=current_uA,
    )


def save_field(field: FEMField, path: str | Path) -> Path:
    """Write a field to ``.npz`` for fast reloading."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out,
        points_um=field.points_um,
        potential_V=field.potential_V,
        current_uA=np.array([np.nan if field.current_uA is None else field.current_uA]),
    )
    return out


def compare_with_point_source(
    field: FEMField,
    current_uA: float,
    sigma_S_per_m: float = 0.35,
    *,
    min_distance_um: float = 1.0,
) -> pd.DataFrame:
    """Compare an imported field against the analytic point-source solution.

    Useful as a sanity check on units and on how far from the electrode the homogeneous
    approximation stays usable. Large deviations near the electrode are expected and
    correct; large deviations far from it usually mean a unit-scale mistake on import.
    """
    from ..models.field import potential_V

    r = np.linalg.norm(field.points_um, axis=1)
    keep = r >= min_distance_um
    if not np.any(keep):
        raise ValueError(
            f"no imported points lie at least {min_distance_um:g} um from the origin; "
            f"is the field centred on the electrode?"
        )
    r_keep = r[keep]
    analytic = np.asarray(potential_V(current_uA, r_keep, sigma_S_per_m))
    fem = field.potential_V[keep]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(analytic != 0, fem / analytic, np.nan)
    return pd.DataFrame(
        {
            "distance_um": r_keep,
            "fem_V": fem,
            "point_source_V": analytic,
            "ratio": ratio,
        }
    ).sort_values("distance_um", ignore_index=True)
