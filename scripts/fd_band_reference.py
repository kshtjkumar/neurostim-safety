#!/usr/bin/env python3
"""Finite-difference reference for the access resistance of a band on an insulating shaft.

There is no compact exact solution for a cylindrical band electrode flush in the surface
of an insulating shaft, which is the geometry of every clinical DBS contact. The package
substitutes an equal-area disc, and a proposed repair substituted ``ln(2L/r)/(2*pi*sigma*L)``.
Neither can be checked against a closed form, so this script computes the answer directly
and the table it prints becomes the reference the tests pin against
(``tests/oracles/fd_band.FD_BAND_REFERENCE``).

The problem
-----------
Axisymmetric Laplace, ``div(sigma grad V) = 0``, in the half-space outside an infinite
insulating cylinder of radius ``r0 = d/2``:

* the band, ``|z| <= h/2`` at ``r = r0``, is held at ``V = 1``
* the rest of the shaft, ``|z| > h/2`` at ``r = r0``, is insulating (zero normal flux)
* ``V -> 0`` far away
* the plane ``z = 0`` is a symmetry plane, so only ``z >= 0`` is solved

``R = V / I`` with ``V = 1``, so ``R = 1/I``, and the current is the flux integrated over
the electrode surface. The discretisation is finite *volume* on a non-uniform grid, which
conserves current exactly cell by cell -- the quantity being measured is a current, so a
scheme that conserves it is worth the small extra effort over plain finite differences.

Grids are geometric in ``r`` from the shaft outwards, and uniform across the band then
geometric beyond it in ``z``, because the solution varies on the scale of the band near
the electrode and on the scale of the domain far from it.

Usage
-----
::

    python scripts/fd_band_reference.py                  # the reference sweep
    python scripts/fd_band_reference.py --convergence    # grid and domain refinement

Runtime is a few seconds per aspect ratio at the default resolution, which is why the
table is frozen in the test tree rather than recomputed on every test run.
"""

from __future__ import annotations

import argparse
import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

SIGMA_S_PER_M = 0.35
"""Grey-matter conductivity used throughout the package."""

SHAFT_DIAMETER_M = 1270e-6
"""Medtronic 3389 lead diameter. Aspect ratio is band height / shaft diameter."""

REFERENCE_ASPECTS = (0.2, 0.39, 0.5, 1.0, 1.181, 2.0, 4.0, 10.0)
"""1.181 is the clinical contact: 1500 um of band on a 1270 um shaft."""


def solve_band_resistance_ohm(
    shaft_radius_m: float,
    band_height_m: float,
    *,
    conductivity_S_per_m: float = SIGMA_S_PER_M,
    nr: int = 500,
    nz: int = 500,
    domain_factor: float = 2000.0,
) -> float:
    """Access resistance of a band of height ``band_height_m`` on an insulating shaft.

    ``domain_factor`` sets where the far-field ``V = 0`` boundary is placed, as a multiple
    of the shaft radius radially and of ``max(band height, shaft radius)`` axially.
    """
    r0 = shaft_radius_m
    half_height = band_height_m / 2.0
    r_max = r0 * domain_factor
    z_max = max(band_height_m, r0) * domain_factor

    # Radial nodes: geometric from the shaft surface out to the far field.
    r = r0 * np.exp(np.linspace(0.0, math.log(r_max / r0), nr))
    # Axial nodes: uniform across the electrode, geometric beyond it.
    n_band = max(2, nz // 3)
    z_band = np.linspace(0.0, half_height, n_band, endpoint=False)
    z_far = half_height * np.exp(np.linspace(0.0, math.log(z_max / half_height), nz - n_band))
    z = np.concatenate([z_band, z_far])

    n_r, n_z = len(r), len(z)

    # Control-volume faces and widths.
    r_face = np.empty(n_r + 1)
    r_face[1:-1] = 0.5 * (r[:-1] + r[1:])
    r_face[0], r_face[-1] = r[0], r[-1]
    dr = np.diff(r_face)

    z_face = np.empty(n_z + 1)
    z_face[1:-1] = 0.5 * (z[:-1] + z[1:])
    z_face[0], z_face[-1] = z[0], z[-1]
    dz = np.diff(z_face)

    on_electrode = z <= half_height + 1e-12

    def index(i: np.ndarray, j: np.ndarray) -> np.ndarray:
        return i * n_z + j

    ii, jj = np.meshgrid(np.arange(n_r), np.arange(n_z), indexing="ij")
    ii, jj = ii.ravel(), jj.ravel()
    node = index(ii, jj)

    dirichlet = (ii == 0) & on_electrode[jj]
    outer = (ii == n_r - 1) | (jj == n_z - 1)
    fixed = dirichlet | outer
    interior = ~fixed

    rows = [node[fixed]]
    cols = [node[fixed]]
    vals = [np.ones(fixed.sum())]
    rhs = np.zeros(n_r * n_z)
    rhs[node[dirichlet]] = 1.0

    i_in, j_in, k_in = ii[interior], jj[interior], node[interior]
    diag = np.zeros(len(k_in))

    # Conductance of a face is (face area) / (node spacing); the common 2*pi cancels.
    def add(mask: np.ndarray, neighbour: np.ndarray, conductance: np.ndarray) -> None:
        rows.append(k_in[mask])
        cols.append(neighbour[mask])
        vals.append(conductance[mask])
        diag[mask] -= conductance[mask]

    inner_r = i_in > 0  # i == 0 off the electrode is the insulating shaft: no flux
    g = np.zeros(len(k_in))
    g[inner_r] = r_face[i_in[inner_r]] * dz[j_in[inner_r]] / (r[i_in[inner_r]] - r[i_in[inner_r] - 1])
    add(inner_r, index(i_in - 1, j_in), g)

    g = r_face[i_in + 1] * dz[j_in] / (r[i_in + 1] - r[i_in])
    add(np.ones(len(k_in), dtype=bool), index(i_in + 1, j_in), g)

    lower_z = j_in > 0  # j == 0 is the symmetry plane: no flux
    g = np.zeros(len(k_in))
    g[lower_z] = r[i_in[lower_z]] * dr[i_in[lower_z]] / (z[j_in[lower_z]] - z[j_in[lower_z] - 1])
    add(lower_z, index(i_in, j_in - 1), g)

    g = r[i_in] * dr[i_in] / (z[j_in + 1] - z[j_in])
    add(np.ones(len(k_in), dtype=bool), index(i_in, j_in + 1), g)

    rows.append(k_in)
    cols.append(k_in)
    vals.append(diag)

    matrix = sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n_r * n_z, n_r * n_z),
    )
    potential = spla.spsolve(matrix, rhs).reshape(n_r, n_z)

    # Current leaving the electrode, across the first radial face, doubled for |z|.
    band = np.flatnonzero(on_electrode)
    flux = 2.0 * math.pi * r_face[1] * dz[band] * (potential[0, band] - potential[1, band])
    current = 2.0 * float(np.sum(flux / (r[1] - r[0])))
    return 1.0 / (current * conductivity_S_per_m)


def equal_area_sphere_ohm(area_cm2: float, conductivity_S_per_m: float = SIGMA_S_PER_M) -> float:
    """``1/(4 pi sigma a)`` for the sphere of the same surface area."""
    area_m2 = area_cm2 * 1e-4
    radius_m = math.sqrt(area_m2 / (4.0 * math.pi))
    return 1.0 / (4.0 * math.pi * conductivity_S_per_m * radius_m)


def equal_area_disc_ohm(area_cm2: float, conductivity_S_per_m: float = SIGMA_S_PER_M) -> float:
    """``1/(4 sigma a)``, Newman's flush disc -- what the package uses today."""
    area_m2 = area_cm2 * 1e-4
    radius_m = math.sqrt(area_m2 / math.pi)
    return 1.0 / (4.0 * conductivity_S_per_m * radius_m)


def band_area_cm2(diameter_m: float, height_m: float) -> float:
    return math.pi * (diameter_m * 1e2) * (height_m * 1e2)


def sweep(nr: int, nz: int, domain_factor: float) -> None:
    print(
        f"sigma = {SIGMA_S_PER_M} S/m, shaft d = {SHAFT_DIAMETER_M * 1e6:.0f} um, "
        f"grid {nr}x{nz}, domain {domain_factor:.0f}x\n"
    )
    print(f"{'aspect h/d':>10} {'h (um)':>8} {'FD (ohm)':>10} {'eq-sphere':>10} {'eq-disc':>10}")
    for aspect in REFERENCE_ASPECTS:
        height = aspect * SHAFT_DIAMETER_M
        resistance = solve_band_resistance_ohm(
            SHAFT_DIAMETER_M / 2.0, height, nr=nr, nz=nz, domain_factor=domain_factor
        )
        area = band_area_cm2(SHAFT_DIAMETER_M, height)
        print(
            f"{aspect:10.3f} {height * 1e6:8.0f} {resistance:10.1f} "
            f"{equal_area_sphere_ohm(area):10.1f} {equal_area_disc_ohm(area):10.1f}"
        )


def convergence() -> None:
    """Refine the grid and push the far field out, at the clinical aspect ratio."""
    height = 1.181 * SHAFT_DIAMETER_M
    print("clinical contact, 1500 um band on a 1270 um shaft\n")
    print(f"{'grid':>10} {'domain':>8} {'R (ohm)':>10}")
    for nr, nz, factor in [
        (300, 300, 300.0),
        (300, 300, 2000.0),
        (500, 500, 1000.0),
        (500, 500, 2000.0),
        (700, 700, 2000.0),
        (700, 700, 3000.0),
    ]:
        resistance = solve_band_resistance_ohm(
            SHAFT_DIAMETER_M / 2.0, height, nr=nr, nz=nz, domain_factor=factor
        )
        print(f"{nr:5d}x{nz:<4d} {factor:8.0f} {resistance:10.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--convergence", action="store_true", help="grid/domain refinement study")
    parser.add_argument("--nr", type=int, default=500)
    parser.add_argument("--nz", type=int, default=500)
    parser.add_argument("--domain-factor", type=float, default=2000.0)
    args = parser.parse_args(argv)

    if args.convergence:
        convergence()
    else:
        sweep(args.nr, args.nz, args.domain_factor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
