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
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..geometry.base import Electrode

_POSITION_ALIASES = {
    "x": ("x", "x_um", "x [um]", "x (um)", "coord_x", "% x"),
    "y": ("y", "y_um", "y [um]", "y (um)", "coord_y"),
    "z": ("z", "z_um", "z [um]", "z (um)", "coord_z"),
}
_POTENTIAL_ALIASES = ("v", "v_v", "potential", "potential_v", "phi", "voltage", "es.v")


def _match_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    """The one column naming this quantity, ``None`` if none does.

    More than one raises: a file carrying both ``x`` (metres) and ``x_um`` silently took
    the metre columns and read positions of 0 to 0.0003 um (ledger 61/M6).
    """
    lowered = {c.strip().lower(): c for c in columns}
    found = [lowered[candidate] for candidate in candidates if candidate in lowered]
    if len(found) > 1:
        raise ValueError(
            f"ambiguous columns {found}: each names the same quantity; drop all but one"
        )
    return found[0] if found else None


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
        # Two samples at one position with different potentials leave the interpolant an
        # arbitrary blend of them (ledger 61/M7).
        unique = np.unique(self.points_um, axis=0).shape[0]
        if unique < self.points_um.shape[0]:
            raise ValueError(
                f"{self.points_um.shape[0] - unique} duplicate position(s) among "
                f"{self.points_um.shape[0]} points; a field has one potential per point"
            )

    @property
    def n_points(self) -> int:
        """Number of sample points."""
        return int(self.points_um.shape[0])

    @property
    def bounds_um(self) -> tuple[np.ndarray, np.ndarray]:
        """Axis-aligned bounding box of the sampled region, ignoring non-finite positions.

        A single NaN position used to turn the whole box into NaN (ledger 61/M8).
        """
        return np.nanmin(self.points_um, axis=0), np.nanmax(self.points_um, axis=0)

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
        # nan-aware, with the count beside it: one NaN printed "potential nan to nan V",
        # destroying the diagnostic the load_field docstring points at (ledger 61/M8).
        bad_v = int(np.count_nonzero(~np.isfinite(self.potential_V)))
        bad_p = int(np.count_nonzero(~np.isfinite(self.points_um).all(axis=1)))
        lines = [
            f"FEM field: {self.n_points} points from {self.source or 'unknown source'}",
            f"  bounds x [{lo[0]:g}, {hi[0]:g}] um, "
            f"y [{lo[1]:g}, {hi[1]:g}] um, z [{lo[2]:g}, {hi[2]:g}] um"
            + (f" ({bad_p} non-finite position(s))" if bad_p else ""),
            f"  potential {np.nanmin(self.potential_V):.4g} to "
            f"{np.nanmax(self.potential_V):.4g} V"
            + (f" ({bad_v} non-finite value(s))" if bad_v else ""),
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

    note = ""
    if p.suffix.lower() == ".npz":
        with np.load(p) as data:
            keys = set(data.files)
            # What save_field recorded comes back with the field; a current passed here
            # that disagrees with it is refused rather than silently preferred
            # (ledger 61/M9).
            if "current_uA" in keys:
                saved = float(np.asarray(data["current_uA"]).ravel()[0])
                if math.isfinite(saved):
                    if current_uA is not None and current_uA != saved:
                        raise ValueError(
                            f"{p.name} was saved at current_uA = {saved:g}; "
                            f"got current_uA = {current_uA:g}"
                        )
                    current_uA = saved
            if "note" in keys:
                note = str(data["note"])
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
        note=note,
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
        note=np.array(field.note),
    )
    return out


def compare_with_point_source(
    field: FEMField,
    current_uA: float,
    sigma_S_per_m: float = 0.35,
    *,
    min_distance_um: float = 1.0,
    electrode: Electrode | None = None,
    check_scale: bool = True,
) -> pd.DataFrame:
    """Compare an imported field against the analytic point-source solution.

    Useful as a sanity check on units and on how far from the electrode the homogeneous
    approximation stays usable. Large deviations near the electrode are expected and
    correct; large deviations far from it usually mean a unit-scale mistake on import.

    Pass the ``electrode`` the field was solved for. Its
    :attr:`~neurostim.geometry.base.Electrode.environment` picks the half-space or the
    full-space point source, and a planar electrode compared against the full-space one
    reads a spurious factor of two far out (physics m4). ``None`` compares against a
    full-space point source.

    With ``check_scale`` (the default) the comparison is also a verdict: when the median
    ratio over a mid-range band of distances (a thirtieth to a third of the largest) is
    off by more than a factor of
    :data:`SCALE_TOLERANCE`, it raises, naming the likely unit mistake. It used to
    return a clean frame with every ratio at 1e6 for a potential column off by a million
    (ledger 61/M5). Pass ``check_scale=False`` when a large far-field deviation is what
    you are looking at.
    """
    from ..models.field import potential_V

    # The field was solved at one current; comparing it against a point source at another
    # returned ratios off by their quotient with no complaint (ledger 62/L5).
    if field.current_uA is not None and current_uA != field.current_uA:
        raise ValueError(
            f"the field was solved at {field.current_uA:g} uA but compared at "
            f"{current_uA:g} uA; rescale it first with field.scale_to_current"
        )
    r = np.linalg.norm(field.points_um, axis=1)
    keep = r >= min_distance_um
    if not np.any(keep):
        raise ValueError(
            f"no imported points lie at least {min_distance_um:g} um from the origin; "
            f"is the field centred on the electrode?"
        )
    r_keep = r[keep]
    analytic = np.asarray(
        potential_V(current_uA, r_keep, sigma_S_per_m, electrode=electrode)
    )
    fem = field.potential_V[keep]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(analytic != 0, fem / analytic, np.nan)
    table = pd.DataFrame(
        {
            "distance_um": r_keep,
            "fem_V": fem,
            "point_source_V": analytic,
            "ratio": ratio,
        }
    ).sort_values("distance_um", ignore_index=True)
    if check_scale:
        # A band chosen by distance, not the farther half by count: a regular grid puts
        # most of its points near the outer boundary, where a grounded solution falls to
        # zero, and a correct export read 0.0931 there (ledger 165). The band runs from a
        # thirtieth to a third of the largest distance -- clear of the electrode and of
        # the boundary -- and falls back to every point when it holds too few.
        distance = table["distance_um"].to_numpy()
        ratios = table["ratio"].to_numpy()
        top = float(distance.max())
        band = ratios[(distance >= top / 30.0) & (distance <= top / 3.0)]
        if np.count_nonzero(np.isfinite(band)) < MIN_BAND_POINTS:
            band = ratios
        median = float(np.nanmedian(band)) if np.isfinite(band).any() else math.nan
        if not (math.isfinite(median) and 1.0 / SCALE_TOLERANCE <= median <= SCALE_TOLERANCE):
            raise ValueError(
                f"far-field FEM/point-source ratio has median {median:.3g}, outside "
                f"1/{SCALE_TOLERANCE:g} to {SCALE_TOLERANCE:g}: a unit-scale mistake is "
                f"likely (potential in mV rather than V, positions in m rather than um -- "
                f"see load_field's position_scale_to_um), or a different current; pass "
                f"check_scale=False if the deviation is real"
            )
    return table


MIN_BAND_POINTS = 5
"""Fewest finite ratios the mid-range band must hold before the check uses it alone."""

SCALE_TOLERANCE = 10.0
"""How far the far-field median ratio may stray from 1 before :func:`compare_with_point_source`
calls it a unit mistake: a decade, well outside any real far-field departure from the
homogeneous model and well inside the 1e3 and 1e6 factors unit slips produce."""
