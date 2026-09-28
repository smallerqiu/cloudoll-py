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
- Use `config/conf.local.yaml` / `conf.prod.yaml`, environment placeholders for secrets, and the documented CLI startup. Cloudoll does not automatically load `.env`. Do not introduce a parallel JSON config system by default.
- Use module-level route decorators from `cloudoll.web` and Pydantic models with `Body`, `Query`, `Path`, or `Form`. Do not rebuild request parsing/validation when these adapters cover the case. Keep writable fields explicit; reject or exclude ownership/permission fields from client input.
- Use documented response helpers and actual HTTP status codes. A JSON `code` property does not set HTTP status. Raw aiohttp responses are appropriate only when their different response contract is intentional.
- Let the framework initialize and close configured databases. Set `orm.default` to a datasource alias. Use ORM models and per-operation queries for normal CRUD; raw SQL is for a concrete unsupported operation, with bound values and whitelisted dynamic identifiers.
- In initialized application routes and their service calls, default to `User.select()`, `User.where(...).update(...)`, and `User.transaction()`, **without `.use(db)`**. Splitting code into service classes does not require passing an engine. Use model `__datasource__` for a fixed named datasource; explicit `.use(engine)` is for an intentional override or standalone/test code without a datasource context. Keep `.use(None)` for offline SQL compilation. Do not remove bindings from context-free scripts mechanically.
- ORM supports `select`, `where`, `join`, `order_by`, `limit`, `offset`, field `like` / `As` / `count`, query `count`, `one`, `one_model`, `all`, and CRUD writes. Use these for ordinary joined/paginated queries, not hand-written SQL just because a query has joins, aliases or aggregates. Exact spellings are `order_by` and `As`. Check JOIN semantics and return types in `database`; do not assume an inner join or dictionary from every `one()`.
- Before adding or retaining raw SQL, identify the specific missing ORM capability in the installed source/docs and explain it at the call site. Existing SQL and convenience are not sufficient reasons. Preserve permissions, count semantics, row locks and transaction ownership when migrating; keep only the unsupported portion at the low level.
- Grouping is already supported: `group_by`, `having`, `sum/avg/min/max`, conditional aggregates, field `distinct`, `In/not_in`, `between`, and NULL predicates. Read database examples for grouping/count semantics; do not infer an ORM gap from an abbreviated API list.
- Cloudoll 4.3.0 adds explicit JOIN kinds, query `distinct`, `one_dict`, `exists`, `subquery/exists_expr/where_exists`, `for_update`, and expression-valued updates. These are not available in 4.2.1 or earlier: verify the installed version before using them, never upgrade dependencies implicitly. Locks require caller-owned transactions; computed updates require reloading records; scalar/IN subqueries project one column and cannot span datasources. See the database topic for examples and restrictions.
- Other 4.3.0 APIs: `Model.alias(name)` exposes qualified fields under `.c` and queries through `.query()`; `query.cte(name)` creates a non-recursive read-only source; `union/union_all` snapshot both branches and return a new query. Name aggregate projections with `As`; use result `.c` for UNION aliases. Query-source writes and locking CTE/UNION sources are rejected. `upsert(values, update_fields=[...])` requires a fresh unfiltered query: PostgreSQL supports `conflict_fields`, MySQL rejects that option because any unique key may trigger its update. Read `database` for full contracts and version availability; do not simulate authorization with `where(...).upsert(...)`.
- Do not perform database work at import time or share mutable query builders globally. `insert()` returns `(success, id)`, not an ID alone. `all()` returns dictionaries. `UNSET` and `None` differ. Consult `database` before selecting result APIs or transactions.
- `cloudoll gen` is not a production migration system. Plan versioned migrations, review destructive changes, and remember MySQL DDL can commit implicitly. Never create or drop a user's database without authorization.

## Topic routing

| Task | Read with `ai read` |
| --- | --- |
| Routes, request bodies, responses | `router`, `validation`, `exception` |
| Database, transactions, models | `database`, `config`, `app-start` |
| Auth and authorization | `jwt`, `middleware`, `cookie-and-session` |
| Startup, resources, background tasks | `app-start`, `middleware` |
| Uploads / streaming | `file-uploads`, `event-source`, `websockets` as applicable |
| HTTP clients / templates | `http-client`, `view` as applicable |
| Deployment or upgrades | `deployment`, `logs`, `migration`, `changelog` |

## Safety and lifecycle

- JWT helpers validate/sign tokens; they do not supply user authentication, permission checks, revocation, or refresh-token policy. `sa_ignore=True` is metadata that your authentication middleware must interpret, not automatic authorization.
- Middleware is `@middleware`; its second argument is `handler`. Return a response and preserve validation/HTTP exceptions and cancellation. Typed request fields may not exist before the controller adapter runs.
- Follow `app-start` hook contracts exactly. `on_task` is an async generator with one yield. Keep transactions in their owning task; do not spread them across `asyncio.gather` tasks. Standalone scripts may explicitly own connections; ordinary applications should use framework lifecycle.
- Never print secrets, log passwords, or commit populated credential files. Use least-privilege database credentials and clearly separate test databases from user data.

## Verify and report

Run the project's checks and test valid/invalid requests, authentication/authorization failures, and database error paths. Use ORM `.use(None).… .test()` to inspect bound SQL without a database when useful; this is not a substitute for integration tests. Never claim a database flow was tested if no database was available. Report the documentation topics consulted, any deliberate deviations, and remaining verification steps.
