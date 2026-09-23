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
7. Merge the release commit into `master`, then push its stable version tag.
   `release.yml` runs the full test and security workflows before publishing
   the tested Python 3.13 wheel and sdist via PyPI Trusted Publishing.

Core dependencies are not an application lockfile. Deploying applications should
lock their resolved dependency graph and scan that exact environment. CI uses a
fresh resolution to catch upstream incompatibilities; release artifacts should
retain the resolved versions used for verification.

## Automated PyPI publishing

Configure the following once before pushing the next release tag:

1. In GitHub repository settings, create an environment named `pypi`. Restrict
   deployment to version tags (`v*`); add required reviewers if manual release
   approval is desired. Protect `master` and release tags against unauthorized
   updates. Environment approvals, when enabled, pause publication after CI.
2. In the existing PyPI `cloudoll` project's Publishing settings, add a GitHub
   Trusted Publisher with owner `smallerqiu`, repository `cloudoll-py`, workflow
   filename `release.yml`, and environment `pypi`. No API-token secret is needed.
   See [PyPI configuration](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

For each release, update the library and scaffold dependency versions and release
notes, merge into `master`, and tag that commit as `vX.Y.Z`. Push `master` before
the tag. Only stable three-part version tags trigger a successful release guard;
the commit must be reachable from `master`, and package metadata must match the
tag. PRs, branch pushes and manual test runs do not publish.

The release job reuses the Linux Python 3.9–3.14 database tests, macOS/Windows
smoke tests and dependency audit. Publication is blocked if any job fails. Only
the isolated upload job receives OIDC permissions; it downloads `release-dist`
from the same workflow run and does not check out or execute project code.

Existing PyPI versions are not overwritten or silently skipped. Do not recreate
`v4.0.0` or upload it again: it was published manually. If an upload partially
succeeds, inspect the PyPI files and their hashes before recovery; do not move
the tag or blindly retry. Creating this workflow does not configure the PyPI
publisher or GitHub environment automatically.
