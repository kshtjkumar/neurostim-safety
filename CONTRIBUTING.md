# Contributing to neurostim-safety

This package reports whether a stimulation protocol is safe for tissue and electrode, and
every number it prints traces to a published source. So a contribution has to keep two
things true: the arithmetic, and the trail from each constant back to its paper. The rules
below exist because each of them was once broken, and the break is recorded in
`CODE_MISTAKES_LOG.md`.

## Setting up

```bash
python -m pip install -e ".[dev]"
```

The `dev` extra pins pytest, pytest-cov, coverage, ruff and mypy exactly, so a new tool
release cannot fail CI with no change in the repository. Raise a pin in its own commit,
along with the fixes the new version needs.

## The gates

Every commit must pass all of these, each checked for its own exit code:

```bash
ruff check neurostim tests examples
mypy neurostim tests
python scripts/ledger_check.py
python scripts/regenerate_example_output.py --check
python scripts/provenance_audit.py --strict
python scripts/build_api_docs.py
pytest -q
```

CI runs the same commands (`.github/workflows/ci.yml`); the API reference is built into a
temporary directory there and not kept. It also runs the branch-point
coverage floor (`scripts/branch_floor.py`), which may be raised but never lowered.

## Changing a number

- **Write the test first, and see it fail for the reason you expect.** A test that passes
  before the fix proves nothing about the fix.
- **Take the expected value from outside the code under test**: a published figure, a
  closed form, or an independently written oracle in `tests/oracles/`. A test that
  recomputes the implementation's own expression only checks that it agrees with itself.
- **Check that the test can fail.** Break the line it guards, confirm the test goes red,
  and restore the line. `scripts/mutation.py` does this systematically (see below).
- **Regenerate derived output**, `example_output/` and the README transcript, with
  `python scripts/regenerate_example_output.py`. Never edit them by hand.
- **Say what moved.** A change that moves a printed number gets a CHANGELOG entry giving
  the old value, the new one, and the configurations it affects.
- **Record an edited test.** If you change an assertion in an existing test, say which one
  and why in the commit message.

## Adding or changing a constant

- Every constant cites an entry in `neurostim/references.py`. Record page, table or
  figure, and the conditions the value was measured under.
- A value read from a paper not in the maintainers' library is cited as secondary: its
  note says "cited via" the paper that quotes it.
- **Never set `verified=True`, or remove a provenance gap, without the source in hand.**
  `scripts/provenance_audit.py --strict` fails on any gap not in its `KNOWN_GAPS` list. It
  also fails on a listed gap that has been closed, so that list can only shrink.
- A DOI must come from the publisher's record (Crossref), matched on title, authors, year,
  venue and pages. Do not recall one from memory.

## The mistakes ledger

`CODE_MISTAKES_LOG.md` records every defect found, and
`docs/audit/FIX_PLAN_v2.md` §9 schedules each one. When you fix a logged defect, record
the commit that fixed it in both places, and run `python scripts/ledger_check.py`.

### Merge policy: no squash-merge, no rebase onto the default branch

The ledger's Commit column records each fix by the hash it had when it was made.
`ledger_check.py` asserts that every recorded hash is a commit in the history. A
squash-merge or a rebase rewrites those hashes, which breaks every row that points at
them. So:

- merge pull requests with a merge commit;
- do not squash;
- do not rebase a branch that has been recorded in the ledger onto the default branch;
- do not force-push the default branch.

## Mutation testing

`scripts/mutation.py` runs mutants against the suite in a temporary copy of the
repository. There are 26 named mutants taken from the test audit, which must all be
killed, and 160 generated from the AST with a fixed seed, of which at least 90 % must be
killed. A full run takes about an hour. It runs on demand and weekly in CI
(`.github/workflows/mutation.yml`), and its results are committed at
`docs/audit/mutation_results.json`. After you change the gated modules, run
`python scripts/mutation.py --check-anchors`: it fails if a named mutant's anchor no
longer matches the code.

## Release checklist

These need the local paper library (`papers_stim_calc_ref/`, not redistributed) or take
too long for every push, so they are run by hand before a release:

1. `python scripts/verify_transcriptions.py --strict --require-papers`. Every transcribed
   value must be found in its cited paper, and every cited paper must be present. CI
   cannot run this blocking, because it has no library.
2. `python scripts/mutation.py`. The gate must be met; commit the refreshed
   `docs/audit/mutation_results.json`.
3. Bump the version in `pyproject.toml` and `CITATION.cff`. `neurostim.__version__` is read
   from the installed metadata, and a test asserts all three agree.
4. Give the release a CHANGELOG section.
5. Run every gate above.
