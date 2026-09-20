# Changelog

## 4.0.0 — Unreleased

### Core production hardening

- Explicitly selected missing configuration files now raise `FileNotFoundError`.
  Use `Application.create(env=None)` or `config={}` for intentional no-config mode.
- Library-owned configuration types/ranges are validated before startup and after
  `on_create`. Custom business/plugin keys remain supported.
- JWT verification requires `exp` by default and supports issuer, audience,
  leeway and required claims. Invalid tokens return `None`; configuration errors
  raise. Explicit `require=()` is the legacy-token escape hatch.
- Native pool close and application resource cleanup have finite deadlines.
- Added JSON logging, structured-data masking, string-redaction extension,
  trace correlation and value-free HTTP/native query observation events.
- Added native deadlock/commit-cancellation regression tests and dependency audit CI.

### Migration

See [reliability](docs/reliability.md) for the existing transaction, savepoint,
UNSET/dirty-field, CLI/PID, SQL echo and request parsing changes. See
[production contracts](docs/production.md) for the new configuration and APIs.

This file does not change package version metadata or publish a release.
