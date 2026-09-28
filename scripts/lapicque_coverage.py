#!/usr/bin/env python3
"""Coverage of the Lapicque chronaxie interval, measured by simulation (ledger 183).

For each design and noise level, draws seeded replicates from a known Lapicque curve
(rheobase 20 uA, chronaxie 200 us), fits them with :func:`neurostim.models.strength_duration.fit_lapicque`,
and reports:

- how many fits were accepted;
- how many of those had their interval withheld (rule A: an interval lying below every
  width tested);
- how many carry the narrow-design caveat (width span below ``NARROW_SPAN``);
- the coverage of the intervals still reported: the fraction that contain 200 us.

The committed output is ``docs/audit/lapicque_coverage.txt``, and the
``StrengthDurationFit`` docstring and the narrow-design caveat quote it. Re-run it after
any change to the fit::

    python scripts/lapicque_coverage.py > docs/audit/lapicque_coverage.txt
"""

from __future__ import annotations

import math
import sys
import warnings

import numpy as np

DESIGNS = {
    "50-800": [50.0, 100.0, 200.0, 400.0, 800.0],
    "20-3200": [20.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0],
    "50-200": [50.0, 100.0, 150.0, 200.0],
    "400-3200": [400.0, 800.0, 1600.0, 3200.0],
    "2000-8000": [2000.0, 4000.0, 6000.0, 8000.0],
}
NOISE = (0.02, 0.05, 0.10, 0.20)
REPLICATES = 600
SEED = 183
TRUE_CHRONAXIE_US = 200.0


def main() -> int:
    from neurostim.models import strength_duration as sd

    tau = TRUE_CHRONAXIE_US / math.log(2.0)
    rng = np.random.default_rng(SEED)
    print(f"fit_lapicque coverage: {REPLICATES} replicates per cell, seed {SEED}, "
          f"rheobase 20 uA, chronaxie {TRUE_CHRONAXIE_US:g} us")
    print(f"{'widths (us)':<11} {'noise':>5} {'accepted':>8} {'withheld':>8} "
          f"{'caveat':>6} {'reported':>8} {'coverage':>8}")
    for name, widths_list in DESIGNS.items():
        widths = np.array(widths_list)
        for noise in NOISE:
            accepted = withheld = caveat = reported = covered = 0
            for _ in range(REPLICATES):
                thresholds = 20.0 / (-np.expm1(-widths / tau)) * (
                    1.0 + noise * rng.standard_normal(widths.size)
                )
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        fit = sd.fit_lapicque(widths, thresholds)
                    except (ValueError, RuntimeError):
                        continue
                accepted += 1
                if fit.chronaxie_ci95_us is None:
                    withheld += 1
                    continue
                reported += 1
                caveat += bool(fit.coverage_caveat)
                low, high = fit.chronaxie_ci95_us
                covered += low <= TRUE_CHRONAXIE_US <= high
            coverage = f"{covered / reported:.3f}" if reported else "-"
            print(f"{name:<11} {noise:>5.0%} {accepted:>8} {withheld:>8} {caveat:>6} "
                  f"{reported:>8} {coverage:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
