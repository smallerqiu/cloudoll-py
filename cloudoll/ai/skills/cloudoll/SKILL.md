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
