# Cloudoll

English | [简体中文](README.zh-CN.md)

Cloudoll 4.0.0 is an aiohttp-based Python library for routing, middleware,
templates, sessions, JWT, database access and application scaffolding.

## Install

Python 3.9+ is required. Install only the optional drivers you use:

```sh
python -m pip install 'cloudoll==4.0.0'
python -m pip install 'cloudoll[mysql,postgres,cache]==4.0.0'
```

The AWS extra requires Python 3.10+. Aurora remains untested; see
[Aurora limitations](docs/aurora.md).

## Quick start

```sh
cloudoll create myapp
cd myapp
python -m pip install -r requirements.txt
cloudoll start -n myapp
```

The generated project targets 4.0.0 and receives a random JWT secret. Controllers
and authentication middleware are examples: replace demo credentials and supply
your own authorization and upload policies before deployment.

A minimal application without a configuration file:

```python
from cloudoll.web import Application

application = Application()

@application.get('/')
async def home(request):
    return {'hello': 'cloudoll'}

if __name__ == '__main__':
    application.create(env=None, entry_model=None).run()
```

By default, create() loads config/conf.local.yaml. An explicitly selected missing
file is an error. Use env=None or config={} only for intentional no-config mode.
Template rendering uses Jinja2, via render_view().

## Production and diagnostics

```sh
cloudoll start -n myapp -env prod -m production
```

Production mode stays in the foreground. Use a process manager for automatic
restarts; do not mix its stop/restart commands with Cloudoll's manual management.
Coordinate request draining, resource cleanup and process termination deadlines.

```python
from cloudoll.logging import configure_logging
configure_logging(format='json', files=False)
```

JSON logging supports structured secret-key masking and a custom string redactor.
Native MySQL/PostgreSQL support opt-in echo=True and echo_params=True; both default
to false. SQL is logged at INFO and parameter output requires both switches.
SQL text itself can contain secrets; avoid enabling this in production.

Application(observer=...) and observation_scope(...) expose value-free HTTP/query
events. Native engines expose pool_stats(). trace_context() correlates log IDs;
it is not a tracing SDK. See [production contracts](docs/production.md).

## Upgrading from 3.0.14

- Replace executable configuration expressions with literal values. Missing
  environment variables/files and invalid core configuration fail explicitly.
- Use private Session/JWT keys. Discard cookies created with old publicly
  derivable keys; share the Session key across workers.
- JWT validation requires exp by default and supports issuer, audience, leeway
  and required claims. Invalid credentials return None; configuration errors
  raise. Explicit require=() permits legacy tokens without an expiry.
- Model.use(db) returns an independent Query. Records track UNSET and dirty
  fields; database errors propagate instead of appearing as empty results.
- Native transactions/savepoints are task-owned. Streams need an async with
  scope. Writes and uncertain COMMIT operations are never automatically retried.
- PostgreSQL ORM inserts use RETURNING. Raw inserts without RETURNING and batch
  inserts do not manufacture a primary key.
- Each Application can be created once. Discovery uses an isolated namespace;
  use package-relative imports for local controller helpers.
- Native pool closure defaults to 10 seconds; application resource closure uses
  a 10-second per-resource limit and a 30-second total budget. These deadlines
  cannot be disabled with None and do not bound arbitrary user cleanup code.
- Development children/reloads create independent applications at the explicit
  project root, including under fork. CLI verifies process identity before stop.
- HTTP Session.max_retries counts total attempts. POST/PATCH and non-replayable
  bodies are not automatically replayed by default.

See [changelog](CHANGELOG.md), [migration details](docs/reliability.md),
[streaming and typing](docs/streaming-and-types.md) and
[schema generation](docs/schema-generation.md). The schema generator is not a
production database migration tool.

## Development and release checks

```sh
python -m pip install -e '.[mysql,postgres,cache,dev]'
python -m ruff check cloudoll tests
python -m mypy
python -m pytest -q -m 'not integration' -k 'not aws'
python -m build
python tests/check_wheel.py dist/cloudoll-4.0.0-py3-none-any.whl
python tests/check_release.py dist/cloudoll-4.0.0-py3-none-any.whl
```

Native integration tests require explicitly configured disposable databases.
See [architecture and verification](docs/architecture.md). AWS tests are excluded
from ordinary CI. Passing CI is not a substitute for workload-specific testing.

## Documentation and maintenance

- [Online documentation](https://cloudoll.chuchur.com)
- [Database](https://cloudoll.chuchur.com/database)
- [Deployment](https://cloudoll.chuchur.com/deployment)
- [Compatibility and release policy](docs/maintenance.md)
- [Security reporting](SECURITY.md)
- [MIT license](LICENSE)
