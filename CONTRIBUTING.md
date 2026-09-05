# Contributing

content-kit is a books-as-code toolchain, licensed under the EUPL-1.2. Contributions are welcome, and
this page is the short version of what makes one easy to merge.

## Setting up

```bash
git clone https://github.com/alpibrusl/content-kit
cd content-kit
python -m pip install -e ./packages/core -e ./packages/bookkit \
                      -e ./packages/podcastkit -e ./packages/mcp
python -m pip install ruff import-linter pytest
```

## What CI will check

Run these before you push and there will be no surprises:

```bash
ruff check packages && ruff format --check packages
lint-imports          # the dependency-arrow contracts
pytest packages
```

### The one rule that is not negotiable

`lint-imports` enforces a one-way dependency arrow, and it is the reason this
project stays comprehensible. `core` never imports a renderer. Renderers never
import each other. They meet through validated data artifacts, never through
function calls.

A change that needs the arrow reversed is a change that needs a different
design, and CI will say so before a reviewer has to. If a contract genuinely
should move, change `.importlinter` in its own commit with the reasoning — not
as a side effect of the feature that ran into it.

## Opening a pull request

**Say what broke, not just what changed.** The commit messages in this
repository lead with the problem and the evidence for it — a measurement, a
failing case, a number. A reviewer should be able to tell from the message
alone whether the change is worth making.

**One change per pull request.** A bug fix and a refactor in the same diff
means neither can be reviewed properly, and the fix cannot be reverted without
losing the refactor.

**Tests that would have caught it.** A fix without a test that fails before it
is a fix that comes back.

## Reporting a bug

Open an issue with the smallest input that reproduces it, the command you ran,
and what you expected instead. A version number helps; so does the output of
`pip show bookkit`.

## Licensing of contributions

By opening a pull request you agree that your contribution is licensed under
the **EUPL-1.2**, the same licence as the rest of this repository. There is no
separate contributor agreement to sign.
