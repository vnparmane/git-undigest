# Release Checklist

Use this checklist when cutting a new release of git-undigest.

## Preparation

- [ ] Ensure you are on the `main` branch with no uncommitted changes.
- [ ] Run the full test suite: `python -m pytest tests/`
- [ ] Run lint: `ruff check .`
- [ ] Run formatter: `black --check src/ tests/ benchmarks/`
- [ ] Run type checker: `mypy src/ --strict`

## Version Bump

- [ ] Update version in `src/git_undigest/__init__.py` (the `__version__`
      variable).
- [ ] Update version in `pyproject.toml`.
- [ ] Update `CHANGELOG.md`:
  - Move "Unreleased" section to the new version.
  - Add the release date.
  - Start a new "Unreleased" section at the top.
- [ ] Commit the version bump:

      git commit -m "chore: bump version to X.Y.Z" \
          src/git_undigest/__init__.py pyproject.toml CHANGELOG.md

## Build

- [ ] Build wheel and sdist:

      rm -rf dist/
      python -m build

- [ ] Check distributions:

      twine check dist/*

## Tag and Release

- [ ] Create an annotated tag:

      git tag -a vX.Y.Z -m "vX.Y.Z"

- [ ] Push the tag:

      git push origin vX.Y.Z

## Verify

- [ ] Wait for the GitHub Actions release workflow to complete.
- [ ] Verify the GitHub Release is created with the built artifacts.
- [ ] Verify the package is published on PyPI:

      pip install git-undigest==X.Y.Z

- [ ] Verify the installed package works:

      git-undigest --version

## Post-Release

- [ ] Open a new "Unreleased" section in `CHANGELOG.md`.
- [ ] Announce the release (if appropriate).
