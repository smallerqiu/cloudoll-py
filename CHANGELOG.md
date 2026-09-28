# Changelog

## 4.3.0

### ORM queries and writes

- Add explicit LEFT/INNER/RIGHT JOIN kinds, query-level DISTINCT, `one_dict()`
  for projected/aggregate rows, and non-consuming `exists()` checks.
- Add parameterized scalar/IN and EXISTS/NOT EXISTS subqueries with snapshot
  semantics and datasource/dialect compatibility checks.
- Add read-only table aliases for self-joins, non-recursive CTEs, and
  UNION/UNION ALL with branch-local and outer pagination semantics.
- Add atomic expression-valued updates and transaction-owned `for_update()`
  row locks, including mutually exclusive NOWAIT and SKIP LOCKED options.
- Add single-statement `upsert()` with explicit update fields; PostgreSQL
  supports conflict targets, while MySQL explicitly rejects that option.
- Export `Relation` and `Subquery` types. Reject writes against aliases,
  CTE/UNION sources and joined queries rather than silently ignoring sources.

### Documentation and verification

- Expand grouping/HAVING, aggregates, default datasource usage and query
  result contracts. Normal application CRUD defaults to entity APIs without
  unnecessary `.use(db)` or handwritten SQL.
- Update bundled AI guidance and version-matched examples, including locking,
  unique constraints, snapshots and unsupported advanced combinations.
- Add MySQL 8.4/PostgreSQL 16 integration coverage for query sources, upserts,
  concurrency, rollback and row-lock contention. Aurora remains unverified.

## 4.2.1

- Correct the AI initialization regression test to compare the original bytes
  rather than assume LF newlines on Windows. Keep preservation and idempotence
  assertions enabled on every platform.
- Normalize the generated full documentation's trailing newline.
- Include all 4.2.0 features. The 4.2.0 tag was blocked by Windows CI and was
  not published to PyPI; 4.2.1 is the replacement release.

## 4.2.0

Backward-compatible AI-assisted development release. Python 3.9+ remains supported.

- Add offline `cloudoll ai list`, `read`, and `search` commands for bundled official
  documentation, with source URLs, version metadata and content integrity checks.
- Add `cloudoll ai init` for existing projects. New scaffolds automatically include
  an AGENTS.md entry and a project-local Cloudoll skill covering documented project
  structure, validation, ORM, resource lifecycle, security and verification.
- Preserve existing project instructions and refuse to overwrite customized skills
  or write through symbolic links. Initialization is repeatable.
- Add documentation synchronization tooling and website LLM discovery assets.
  Test both instruction initialization and AI resources in the built wheel.

## 4.1.0

Backward-compatible feature release. Pydantic 2 (`>=2.0,<3`) is now a core
runtime dependency. Existing handlers and explicit ORM engine bindings remain
supported. Python 3.9+ remains supported by the CI matrix.

Publication date is recorded by the release tag/PyPI; preparing these files does
not publish the package.

- Correct lifecycle callback and JWT payload type declarations for strict
  checking with current dependency annotations.
- Include HTTP method and actual request path in exception logs; emit 4xx access
  logs at WARNING and 5xx at ERROR so failed requests remain visible above INFO.

- Add Pydantic 2 request validation with typed `Body`, `Query`, `Form`, and
  `Path` bindings, repeated collection parameters and structured HTTP 400 errors.
  Preserve legacy request and streaming multipart handlers.

- Add application-local named ORM datasources via `orm.default` and model
  `__datasource__`, independent class-level queries, `Model.query()` and
  `Model.transaction()`. Reuse existing task-owned engine transactions.
- Add `datasource_context` for scoped standalone/test engine bindings. Keep
  explicit `.use(engine)`, offline SQL compilation and bound records compatible.

## 4.0.0

Release notes for 4.0.0. Publication date is recorded by the release tag/PyPI;
preparing these files does not publish the package.

### Breaking changes and migration

- Python 3.9+ is required; database/cache drivers are optional extras.
- Configuration values no longer execute Python expressions. Supply literal
  numeric values and inject required environment variables explicitly.
- `Model.use()` returns an independent Query. Records use UNSET and dirty-field
  snapshots; successful outer commits update the saved baseline. Database errors
  propagate instead of appearing as empty results.
- PostgreSQL ORM inserts use RETURNING. Raw inserts without RETURNING and batch
  inserts do not manufacture a primary key.
- Sessions require a private, stable key for multi-worker/restart persistence;
  discard cookies created with old publicly derivable keys.
- Middleware uses the direct async decorator contract. Application creation is
  instance-local and may only be performed once per instance.
- CLI service identity includes process creation time and command line. Unknown
  legacy PID identities are not killed automatically; stop old services safely
  before upgrading. Production mode remains foreground, not a process supervisor.

### ORM and developer experience

- Added native MySQL/PostgreSQL transactions, nested savepoints, scoped streaming,
  generic Query/Field typing and dialect-specific schema generation.
- Added opt-in SQL/parameter echo, connection/query/cleanup timeouts, and safe
  cancellation. Writes and uncertain commits are never automatically replayed.
- Added isolated route/module discovery and explicit application components.
- Development children and reloads create a fresh Application at the explicit
  project root instead of inheriting a parent's cached app/context through fork.
- Scaffold dependencies now target Cloudoll 4.0.0; scaffold business code remains
  illustrative, not a complete application authorization system.

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

Aurora transactions and connection reuse are implemented but remain untested.
Native driver validation must not be presented as Aurora failover validation.
