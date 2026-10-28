---
name: cloudoll
description: Build, review, and migrate Python applications using Cloudoll. Use when a project depends on Cloudoll or a task requests Cloudoll routes, middleware, configuration, validation, authentication, or ORM/database code.
---

# Cloudoll application development

## Read before coding

1. Check the project's dependency pin and `python -m cloudoll.cli --version` in its environment. Do not upgrade dependencies without authorization.
2. Run `python -m cloudoll.cli ai list`. Read complete topics with `python -m cloudoll.cli ai read TOPIC`; search with `python -m cloudoll.cli ai search QUERY`. These are bundled official documentation, not generated API guesses.
3. For new applications read `start`, `structure`, `config`, `router`, `validation`. For existing applications read the relevant topics below and preserve intentional conventions. If the installed version predates the AI commands, consult its README/source and matching release documentation at https://cloudoll.chuchur.com; do not assume current docs apply to an older release.
4. State any meaningful deviation from the documented defaults and its reason before implementing it. If docs and installed signatures disagree, inspect source/tests and report the mismatch.

## Default architecture

- Start new apps with `cloudoll create PROJECT`. Controllers and middlewares are automatically discovered; services and models are explicitly imported. Use documented relative imports inside the isolated application namespace, not `sys.path` hacks or direct execution of controller files.
- Use `config/conf.local.yaml` / `conf.prod.yaml`, environment placeholders for secrets, and the documented CLI startup. EnvYAML automatically reads `.env` from the current working directory, or the file specified by the process environment variable `ENV_FILE`. The YAML `root` does not change this lookup; `-env prod` does not select `.env.prod`. File variables override same-name process variables in the current EnvYAML implementation, but are not written to `os.environ`; use the loaded configuration rather than assuming `os.getenv()` can read them. Keep secrets out of version control. `cloudoll create` writes independent `CLOUDOLL_JWT_SECRET` and `CLOUDOLL_SESSION_SECRET` values to `.env`, and the YAML refers to both by placeholder; keep the placeholders so a deployment can inject its own values. Without a stable session key, every restart and every worker invalidates existing sessions. Do not introduce a parallel JSON config system by default.
- Use module-level route decorators from `cloudoll.web` and Pydantic models with `Body`, `Query`, `Path`, or `Form`. Do not rebuild request parsing/validation when these adapters cover the case. Keep writable fields explicit; reject or exclude ownership/permission fields from client input.
- Use documented response helpers and actual HTTP status codes. A JSON `code` property does not set HTTP status. Raw aiohttp responses are appropriate only when their different response contract is intentional.
- Let the framework initialize and close configured databases. Set `orm.default` to a datasource alias. Use ORM models and per-operation queries for normal CRUD; raw SQL is for a concrete unsupported operation, with bound values and whitelisted dynamic identifiers.
- In initialized application routes and their service calls, default to `User.select()`, `User.where(...).update(...)`, and `User.transaction()`, **without `.use(db)`**. Splitting code into service classes does not require passing an engine. Use model `__datasource__` for a fixed named datasource; explicit `.use(engine)` is for an intentional override or standalone/test code without a datasource context. Keep `.use(None)` for offline SQL compilation. Do not remove bindings from context-free scripts mechanically.
- ORM supports `select`, `where`, `join`, `order_by`, `limit`, `offset`, field `like` / `As` / `count`, query `count`, `one`, `one_model`, `all`, and CRUD writes. Use these for ordinary joined/paginated queries, not hand-written SQL just because a query has joins, aliases or aggregates. Exact spellings are `order_by` and `As`. Check JOIN semantics and return types in `database`; do not assume an inner join or dictionary from every `one()`.
- Before adding or retaining raw SQL, identify the specific missing ORM capability in the installed source/docs and explain it at the call site. Existing SQL and convenience are not sufficient reasons. Preserve permissions, count semantics, row locks and transaction ownership when migrating; keep only the unsupported portion at the low level.
- Grouping is already supported: `group_by`, `having`, `sum/avg/min/max`, conditional aggregates, field `distinct`, `In/not_in`, `between`, and NULL predicates. Read database examples for grouping/count semantics; do not infer an ORM gap from an abbreviated API list.
- Cloudoll 4.3.0 adds explicit JOIN kinds, query `distinct`, `one_dict`, `exists`, `subquery/exists_expr/where_exists`, `for_update`, and expression-valued updates. These are not available in 4.2.1 or earlier: verify the installed version before using them, never upgrade dependencies implicitly. `for_update()` requires a caller-owned transaction and raises outside one; computed updates require reloading records; scalar/IN subqueries project one column and cannot span datasources. See the database topic for examples and restrictions.
- Other 4.3.0 APIs: `Model.alias(name)` exposes qualified fields under `.c` and queries through `.query()`; `query.cte(name)` creates a non-recursive read-only source; `union/union_all` snapshot both branches and return a new query. Name aggregate projections with `As`; use result `.c` for UNION aliases. Query-source writes and locking CTE/UNION sources are rejected. `upsert(values, update_fields=[...])` requires a fresh unfiltered query: PostgreSQL and SQLite support `conflict_fields`, MySQL rejects that option because any unique key may trigger its update. Read `database` for full contracts and version availability; do not simulate authorization with `where(...).upsert(...)`.
- Cloudoll 4.5.0 adds a native SQLite engine and first-class HTTPS. SQLite datasources (`sqlite:///app.db`, `sqlite:///:memory:`) support transactions with `DEFERRED` / `IMMEDIATE` / `EXCLUSIVE`, nested savepoints, streaming, `upsert` with `conflict_fields`, and `cloudoll gen`. SQLite has no row locks: `for_update()` raises at compile time, so serialize writes with `transaction(mode="IMMEDIATE")` instead. An offset without a limit returns the full remainder on every driver; do not pass a fake huge limit for SQLite. Relative SQLite file paths follow the process working directory, and `journal_mode: WAL` is the option for concurrent readers plus one writer.
- SQLite reverse engineering restores literal defaults, `CURRENT_TIMESTAMP` and an explicit `AUTOINCREMENT` counter (which requires `INTEGER PRIMARY KEY`); expression defaults such as `datetime('now')`, and generated columns, raise instead of silently becoming plain columns — hand-write those models. Generated SQLite DDL inlines defaults because the dialect rejects bind parameters inside `CREATE TABLE`.
- HTTPS works the same under `cloudoll start` and `Application.run()`: set `server.ssl_certfile` plus `server.ssl_keyfile` (they must be paired), or a Python `server.ssl_context`, which is mutually exclusive with the paths. Relative certificate paths resolve against the application root, and a missing, unreadable or mismatched certificate fails startup instead of quietly serving plain HTTP. Enable `session.secure` when the site is HTTPS-only.
- The behaviours in the three bullets above landed in **4.5.1**; 4.5.0 shipped the SQLite engine and `Application.run()` TLS, but its development reloader ignored the certificate options, an offset without a limit raised `datatype mismatch` on SQLite, an unmanaged engine blocked interpreter exit, `cloudoll gen` mangled SQLite defaults and counters, and `cryptography` was undeclared so `cloudoll.utils.password` could fail to import. On a project pinned to 4.5.0, report the pin and recommend raising it to 4.5.1 rather than coding around the defect (no fake huge limit, no manual WAL checkpoint, no hand-written model to replace a broken `gen`).
- Do not perform database work at import time or share mutable query builders globally. `insert()` returns `(success, id)`, not an ID alone. `all()` returns dictionaries. `UNSET` and `None` differ. Consult `database` before selecting result APIs or transactions.
- Use `render_view(template, context_dict)` with the context positional; its keyword arguments are `aiohttp.web.Response` options, and an unexpected keyword raises `TypeError` instead of silently becoming template data.
- `cloudoll.utils` (reversible encryption, one-way digests, random strings, distributed IDs) and `cloudoll.mail.smtp` (outgoing email only; the library does not receive mail) are documented APIs — read `utils` and `mail` before rolling a parallel helper. None of the digest helpers are password hashes: store user passwords with bcrypt or argon2.
- `cloudoll gen` is not a production migration system. Plan versioned migrations, review destructive changes, and remember MySQL and SQLite DDL commit implicitly. Never create or drop a user's database without authorization.

## Topic routing

| Task | Read with `ai read` |
| --- | --- |
| Routes, request bodies, responses | `router`, `validation`, `exception` |
| Database, transactions, models | `database`, `config`, `app-start` |
| Auth and authorization | `jwt`, `middleware`, `cookie-and-session` |
| Startup, resources, background tasks | `app-start`, `middleware` |
| Uploads / streaming | `file-uploads`, `event-source`, `websockets` as applicable |
| HTTP clients / templates | `http-client`, `view` as applicable |
| Encryption, digests, random strings, distributed IDs | `utils` |
| Sending email | `mail` |
| Deployment or upgrades | `deployment`, `logs`, `migration`, `changelog` |

## Safety and lifecycle

- JWT helpers validate/sign tokens; they do not supply user authentication, permission checks, revocation, or refresh-token policy. `sa_ignore=True` is metadata that your authentication middleware must interpret, not automatic authorization.
- Middleware is `@middleware`; its second argument is `handler`. Return a response and preserve validation/HTTP exceptions and cancellation. Typed request fields may not exist before the controller adapter runs.
- Follow `app-start` hook contracts exactly. `on_task` is an async generator with one yield. Keep transactions in their owning task; do not spread them across `asyncio.gather` tasks. Standalone scripts may explicitly own connections; ordinary applications should use framework lifecycle.
- Never print secrets, log passwords, or commit populated credential files. Use least-privilege database credentials and clearly separate test databases from user data.

## Verify and report

Run the project's checks and test valid/invalid requests, authentication/authorization failures, and database error paths. Use ORM `.use(None).… .test()` to inspect bound SQL without a database when useful; this is not a substitute for integration tests. Never claim a database flow was tested if no database was available. Report the documentation topics consulted, any deliberate deviations, and remaining verification steps.
