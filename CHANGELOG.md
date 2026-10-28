# Changelog

## 4.5.0

### HTTPS

- `server.ssl_certfile` plus `server.ssl_keyfile`, or a Python `server.ssl_context`,
  serve HTTPS. The development reloader (`cloudoll start`) uses the same settings as
  production `Application.run()`, so a TLS-only site no longer behaves differently
  locally, and the ready message shows the real `https://` address.
- Relative certificate paths are resolved from the application root, like templates and
  static files. Missing, unreadable, half-configured or mismatched certificates fail at
  startup and name the option and path involved instead of falling back to plain HTTP.
  `ssl_context` and certificate paths cannot be combined.

### SQLite

- New async SQLite engine on `aiosqlite`, declared as a runtime dependency: ORM queries,
  bound parameters, batch writes, transactions, nested savepoints, streaming reads,
  `upsert` with `conflict_fields`, and `cloudoll gen` model/table generation.
- Datasources accept `sqlite:///app.db` and `sqlite:///:memory:` (an in-memory database
  keeps its pool at one connection). Options: `maxsize` (default 5), `journal_mode`
  (`WAL` recommended for concurrent readers), `foreign_keys` (on by default),
  `timeout` / `sqlite_timeout`, `close_timeout`.
- `transaction(mode=...)` accepts `DEFERRED`, `IMMEDIATE` and `EXCLUSIVE`; take the write
  lock with `IMMEDIATE` when several writers compete. SQLite has no row locks, so
  `for_update()` raises instead of being silently dropped.
- Paging with only `offset()` returns the remaining rows on every driver; you no longer
  need a large fake `limit()`, and a MySQL-sized limit is never sent to SQLite.
- An engine nobody closed no longer hangs interpreter exit, and a `WAL` journal is still
  merged back into the database file on the way out. `close()` waits for borrowed
  connections to come back without spinning the CPU.
- Reverse engineering a SQLite table restores literal defaults, `CURRENT_TIMESTAMP` and
  an explicit `AUTOINCREMENT` counter. Expression defaults such as `datetime('now')`, and
  generated columns, are refused with a clear message rather than turning into plain
  columns. Generated `AUTOINCREMENT` requires `INTEGER PRIMARY KEY`.

简体中文见 [CHANGELOG.zh-CN.md](CHANGELOG.zh-CN.md)。

## 4.4.0

Defect-fix release; backward compatible. Python 3.9+ remains supported.

### Database

- `for_update()` row locks now require your own transaction. Outside one, the lock
  was released by the commit that `for_update()` issued itself and protected
  nothing; such a call now raises instead of silently doing nothing.
- A transaction cancelled or timed out while waiting for a connection gives that
  connection back to the pool, so long-running services stop losing connections.
- Model fields are hashable again: columns can go into sets and serve as dict
  keys (deduplicating columns, excluding groups of fields).
- `SUM(DISTINCT column)` and similar aggregate deduplication now happens inside
  the aggregate, so values are deduplicated before being combined, and a literal
  inside an aggregate is no longer bound twice.
- URL query parameters in an AWS datasource string are no longer handed to the
  driver as unknown connection options.

### Web and templates

- A response that has already started streaming keeps its body when an error
  occurs; the JSON error handler no longer rewrites it. Streaming and SSE
  endpoints stay intact.
- Page responses no longer repeat `charset` in `Content-Type`.
- `session` options (`key`, `max_age`, `httponly`, `secure`, `domain`, `path`,
  `samesite`) apply to encrypted cookie, Redis and Memcached storage alike.
- `render_view()` keywords are `Response` options only, and the template context
  is the positional mapping. A stray keyword now raises `TypeError` instead of
  being silently merged into the context.
- Development servers bind to 127.0.0.1 by default and no longer occupy
  `port + 1`.
- `server.ignore_dirs` is honoured for directories such as `logs`, so writing logs
  no longer triggers a reload.
- The scaffolded authorization middleware now matches its documentation: it is an
  async decorator, lets static paths through, and lets downstream failures reach
  the error layer instead of being flattened into a 500 that echoes the exception
  text.

### Command line and new projects

- `cloudoll create` no longer copies `__pycache__` and `.pyc` files into the new
  project.
- The last component of a project name must be letters, digits, underscore, dot
  or dash; names with spaces or shell characters are refused, as is an existing
  target directory.
- A failed creation exits with a non-zero status and removes the half-written
  project instead of leaving it behind.
- New projects write independent JWT and session keys to `.env`, which
  `.gitignore` keeps out of version control. Local starts no longer warn about a
  random process-local session key, and logins survive a restart or an added
  worker.

### Mail and utilities

- Building a `cloudoll.mail.smtp.Client` no longer reaches the network, and one
  client stays usable across sends and server idle timeouts: each `send()` opens
  its own connection, carries one copy of the body, and closes the connection even
  when the send fails.
- Missing credentials and an empty recipient address now raise a readable error
  before anything is sent.
- `cloudoll.utils` - reversible encryption, keyed digests, random strings and the
  distributed ID generator - is now official API with a
  [utilities](https://cloudoll.chuchur.com/utils) page and regression tests. None
  of them is a password hash; store user passwords with bcrypt or argon2.
- New [mail](https://cloudoll.chuchur.com/mail) page documents sending limits
  (SMTPS 465 only, no STARTTLS, no retry or queue). The dead POP3 draft under
  `cloudoll/mail` is gone - Cloudoll does not receive mail.

### Upgrade notes

- `for_update()` outside a transaction and unexpected `render_view()` keywords now
  raise rather than misbehaving quietly; audit those two call shapes before
  upgrading.
- `cloudoll create` rejects names it used to accept, such as `my shop`, because
  they reached a shell unsafely.
- Projects created before this release keep an old `config/conf.local.yaml`
  without a session key; add `session.secret_key` (or set
  `CLOUDOLL_SESSION_SECRET`) so sessions survive restarts and multiple workers.
- Existing `.env` files need the new `CLOUDOLL_SESSION_SECRET` entry; `.env` has
  always been ignored by the project's `.gitignore`.

### Documentation

- JWT middleware examples use `web.RequestKey` instead of a plain string key, so
  aiohttp stops warning about it.
- The quick start and session pages describe how a new project injects its keys.

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

This release contains breaking changes to configuration, security, ORM and the
application lifecycle. Read the migration guide before upgrading.

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
