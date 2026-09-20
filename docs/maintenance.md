# Compatibility and release policy

## Public contracts

- Public imports documented in README/docs and non-underscore methods there are
  supported APIs. Internal modules/underscore methods are implementation details.
- Major versions may break public contracts and must document migration steps.
  Minor versions add backward-compatible features. Patch versions fix defects;
  urgent security corrections may tighten invalid/unsafe input handling and must
  be called out in release notes.
- Planned public API removals should first emit `DeprecationWarning` and appear
  in release notes for at least one minor release before a major-version removal.
- This is a maintenance policy, not a paid support or availability SLA.

## Verification matrix

The authoritative matrix is `.github/workflows/tests.yml`: Linux CPython
3.9–3.14 with MySQL 8.4/PostgreSQL 16; macOS/Windows CPython 3.13 smoke tests.
Passing compatibility tests does not imply upstream security support for an old
Python version. Other database/server versions require application validation.
Aurora is explicitly excluded from runtime tests. PyPy has no CI verification.

## Release checklist

1. Review migrations, changelog and template/core responsibility boundaries.
2. Set `cloudoll.__version__` to the intended release, build in a clean checkout,
   and verify the release tag equals `v` plus the packaged version. Unreleased
   changelog entries alone never determine the published version.
3. Require the tests/package and dependency-security workflows to pass. Repository
   branch protection must be configured by the repository administrator; adding
   workflow files alone does not enforce merge protection.
4. Inspect the dependency audit and actual resolved versions. Fix findings or
   document a narrowly reviewed exception; do not disable the audit globally.
5. Run native fault tests against disposable databases. Never point tests at a
   production database. Run workload-specific load/soak tests before deployment.
6. Check wheel/sdist metadata with `twine check`, run wheel smoke checks, and
   install the wheel into a clean environment. Store CI artifacts for review.
7. Publish through a maintainer-controlled release process; prefer PyPI Trusted
   Publishing. This repository change does not configure credentials or publish.

Core dependencies are not an application lockfile. Deploying applications should
lock their resolved dependency graph and scan that exact environment. CI uses a
fresh resolution to catch upstream incompatibilities; release artifacts should
retain the resolved versions used for verification.
