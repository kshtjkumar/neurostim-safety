#!/usr/bin/env python3
"""Build the API reference from the docstrings, with every warning an error.

The reference is generated, not written: ``pdoc`` renders each module's docstrings to
HTML under ``docs/api/``. The output is not committed (``.gitignore``), for the same
reason ``example_output/`` is not: it is a function of the source, and rebuilding it on
demand is cheaper than keeping two copies in step. Nothing is published or hosted.

Every module is covered explicitly. ``pdoc`` given only the package documents just the
submodules its ``__all__`` names, which left most of the package out. A spec also brings
in its own public submodules, so each module is passed only if no earlier spec already
covers it; ``pdoc`` warns (an error here) on a module added twice.

Usage
-----
::

    python scripts/build_api_docs.py                 # writes docs/api/index.html
    python scripts/build_api_docs.py --output-dir D  # somewhere else (CI uses a temp dir)

CI runs it in the ``api-docs`` job. A warning while importing or rendering any module,
such as a docstring that does not parse or a reference that does not resolve, fails
the build.
"""

from __future__ import annotations

import argparse
import pkgutil
import sys
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "api"


def modules() -> list[str]:
    """Every importable module of the package, in a fixed order."""
    import neurostim

    names = ["neurostim"]
    for info in pkgutil.walk_packages(neurostim.__path__, prefix="neurostim."):
        # ``python -m neurostim.gui`` runs the application when imported.
        if info.name.endswith(".__main__"):
            continue
        names.append(info.name)
    return sorted(names)


def specs(names: list[str] | None = None) -> list[str]:
    """The fewest module specs that together cover every module once."""
    from pdoc.extract import walk_specs

    names = modules() if names is None else names
    chosen: list[str] = []
    covered: set[str] = set()
    for name in names:
        if name not in covered:
            chosen.append(name)
            covered.update(walk_specs([name]))
    missing = set(names) - covered
    if missing:
        raise RuntimeError(f"modules not covered by any spec: {sorted(missing)}")
    return chosen


def build(output_dir: Path, names: list[str] | None = None) -> list[Path]:
    """Render ``names`` (default: the whole package) and return the pages written."""
    import pdoc
    import pdoc.render

    import neurostim

    pdoc.render.configure(
        docformat="numpy",
        footer_text=f"neurostim-safety {neurostim.__version__}",
        search=True,
        show_source=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        pdoc.pdoc(*specs(names), output_directory=output_dir)
    return sorted(output_dir.rglob("*.html"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    pages = build(args.output_dir)
    print(f"{len(pages)} pages, {len(modules())} modules -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
