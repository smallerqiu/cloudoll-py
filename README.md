# 🔥🔥🔥 Cloudoll

[English](README.md) | [简体中文](README.zh-CN.md)

Quickly create web applications based on Python.

## Documentation

[Docs](https://cloudoll.chuchur.com)

[Structure](https://cloudoll.chuchur.com/structure)

[Config](https://cloudoll.chuchur.com/config)

[Middleware](https://cloudoll.chuchur.com/middleware)

[Router](https://cloudoll.chuchur.com/router)

[View](https://cloudoll.chuchur.com/view)

[Cookie and Session](https://cloudoll.chuchur.com/session-cookie)

[Upload file](https://cloudoll.chuchur.com/file-uploads)

[WebSocket](https://cloudoll.chuchur.com/websockets)

[Mysql](https://cloudoll.chuchur.com/mysql)

[Deployment](https://cloudoll.chuchur.com/deployment)

## Install
```sh
pip install cloudoll

```

## Environment 

- Operating System: Supports macOS, Linux, Windows
- Runtime Environment: Python 3.9 or newer.

Database drivers are optional. Install the drivers your application uses:

```sh
pip install 'cloudoll[mysql]'
pip install 'cloudoll[postgres]'
pip install 'cloudoll[aws]'
pip install 'cloudoll[cache]'
```

### SQL debug logging

Native MySQL/PostgreSQL SQL debug logging can be enabled per connection with
`echo=True` (SQL) and optionally `echo_params=True` (bound values). Both default
to false. SQL is logged at INFO through the `cloudoll` logger; library users
must configure logging, while the CLI already does. See the
[Chinese SQL logging examples](README.zh-CN.md#orm-sql-调试日志). Avoid enabling
parameter logs in production; SQL literals can also contain sensitive data.
This option does not enable Aurora logging.

### Upgrading from 3.0.14

- Replace arithmetic strings such as `3600 * 24 * 7` in `session.max_age`,
  `jwt.exp`, and `server.client_max_size` with integers (for example `604800`).
  Configuration values are no longer executed as Python code.
- Set `session.secret_key` or `CLOUDOLL_SESSION_SECRET` to a long random secret
  shared by all workers. Without it, each application uses an ephemeral random
  key and sessions expire on restart. Old cookies must be discarded because
  the previous publicly derived key was insecure. `httponly` defaults to true;
  set `session.secure: true` when serving over HTTPS.
- Scaffolded projects receive a unique JWT secret. Existing deployments should
  replace the example `cloudoll_jwt` key. Missing environment variables in YAML
  now fail configuration loading instead of becoming literal secrets.
- Database failures and email delivery failures now propagate to callers.
  PostgreSQL ORM inserts use `RETURNING` for the primary key; raw inserts
  without `RETURNING`, and batch inserts, return `None` for the ID.
- `Model.use(pool)` binds only the returned query to that pool. Keep using the
  returned object; it no longer changes other queries or the model class.
- Each `Application` can be created once. Use a new instance for another app.
  Module-level decorators remain supported; controllers discovered during
  creation are registered against that application.
- HTTP `Session.max_retries` retains its historical meaning of total attempts.
  POST/PATCH are attempted once unless `retry_non_idempotent=True` is explicitly
  enabled. Retried requests must have replayable bodies.

### Development checks

Native MySQL/PostgreSQL now support scoped server-side streaming, with generic
`Query[Model]` annotations and `one_model()` for typed record lookup.
Nested transactions/savepoints and `Field[T]` value inference are supported, and
strict mypy checks cover the complete library. See [streaming and typing](docs/streaming-and-types.md)
and [transaction boundaries](docs/reliability.md) for limitations. Aurora remains untested.

The CLI schema generator now emits dialect-specific native MySQL/PostgreSQL DDL
with bound defaults/comments. See [schema generation](docs/schema-generation.md)
for supported metadata and explicit limitations; it is not a migration tool.

See [reliability migration notes (Chinese)](docs/reliability.md) for native
transactions, UNSET/dirty tracking, timeouts, opt-in logging and request parsing.
These changes are currently source-only. AWS wrapper transactions and connection
reuse are implemented but not yet tested; see [Aurora integration notes](docs/aurora.md).

See [architecture and integration testing (Chinese)](docs/architecture.md) for the
record/query split, application components, migration notes and real database tests.

```sh
python -m pip install -e '.[mysql,postgres,aws,cache,dev]'
python -m ruff check cloudoll tests
python -m mypy
python -m pytest -q
python -m build
```

Tests use simulated database connections and local HTTP servers. Live database
connectivity and AWS failover require an integration environment.

## Quick Start

Now you can use `cloudoll create myapp` to create a new project, 3 steps to start:

1. create a new project
```sh
$ cloudoll create myapp
```
2. cd to project directory
```sh
$ cd myapp
```
3. start dev server
```sh
cloudoll start -n myapp
```
You can also manually create a project step by step. 

```sh
$ mkdir cloudoll-demo && cd cloudoll-demo
$ pip3 install cloudoll
$ vi app.py
```

`app.py` content:

```python
## /app.py
from cloudoll.web import app


if __name__ == "__main__":
    app.create().run()
```

### Controller

```sh
$ mkdir -p controllers/home
$ touch controllers/home/__init__.py
$ vi controllers/home/index.py
```

`controllers/home/index.py` content:

```python
# /controllers/home/index.py
from cloudoll.web import get

@get('/')
async def home():
    return {"name": "cloudoll" ,"msg": "ok"}
```

run:
```sh
$ python3 app.py
$ open http://localhost:9001
```

Open in browser [http://127.0.0.1:9001/](http://127.0.0.1:9001/)

you can see the result:

```json
{ 
    "name": "cloudoll" ,
    "msg": "ok" ,
    "timestamp": 1681993906410 
}
```

Congratulations, you have successfully written one `Restful API` with `cloudoll`. 


### Template rendering

In most cases, we need to read the data, render the template, and then present it to the user. Therefore, we need to introduce the corresponding template engine.

in this demo，we using [Nunjucks](https://mozilla.github.io/nunjucks/) to render template.
```sh
$ mkdir templates
$ vi templates/index.html
```

`index.html` contents:

```html
<!-- /templates/index.html -->

<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Home</title>
</head>
<body>
    <p>Hello {{name}}</p>
</body>
</html>
```


edit `/controllers/home/index.py` contents:

```python
# /controllers/home/index.py
from cloudoll.web import get, render_view

@get('/')
async def home():
    data = {"name": "cloudoll" ,"msg": "ok"}
    return render_view("index.html",data)
```

at this time ,we can see  `“Hello cloudoll.`

ok , we wrotten a view page.

### static files

We want to embed static resources such as images, JS, and CSS in the template, which requires the use of static resources. We place these `js`, `css`, and `image` files in the `static` directory.

For online environments, it is recommended to deploy to a CDN or use servers like `nginx`.

```sh
$ mkdir -p static/img
$ mkdir -p static/js
$ mkdir -p static/css
```
in `img` directory ,we can put images resources.

make a new js file `index.js` ,contents:

clike the body , we can see the alert tip "hello world"
```js
// /static/js/index.js
document.addEventListener('DOMContentLoaded',function(){
    document.body.addEventListener('click',function(){
        alert('hello cloudoll.')
    })
})
```
make a new css file `index.css` ,contents:
```css
 /* /static/css/index.css */
html,
body {
  width: 100%;
  height: 100%;
  color: rgb(0, 229, 255);
  margin: 0;
  padding: 0;
}
```

edit the view page `/templates/index.html` ,in `head` we import the css file, like this:

```html
<!-- /templates/index.html -->
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/static/img/logo.png"/>
    <link rel="stylesheet" href="/static/css/index.css">
    <script src="/static/js/index.js"></script>
    <title>Home</title>
</head>
<body>
    <p>My name is {{name}}</p>
</body>
</html>
```

we create a config file, and config static resource.
```sh
$ mkdir config
$ vi config/conf.local.yaml
```

`/config/conf.local.yaml` contents:

```yaml
server:
  static:
    prefix: /static
```

after reload the page , our changes will be reflected.

### Middleware

Suppose there is a requirement: our news site prohibits access by Baidu crawlers.

so we need to write a middleware to check User-Agent. like this:

```sh
$ mkdir middlewares
$ vi middlewares/robot.py
```

edit `middlewares/robot.py`, contents:

```python
# /middlewares/robot.py
from cloudoll.web import middleware, render_json
import re

@middleware()
def mid_robot():
    async def robot(request, handler):
        ua = request.headers.get('user-agent')
        if re.match('Baiduspider', ua):
            return render_json(status=403, text="Go away , robot.")
        return await handler(request)

    return robot
```
after restart the  server, you can use `curl http://localhost:9001/news -A "Baiduspider"` to see the effect.
we can see more information in [Middleware](https://cloudoll.chuchur.com/middleware)

### Configuration
When writing business logic, it is inevitable to have configuration files. Managing configurations through code involves adding configurations for multiple environments within the code, and passing the parameter of the current environment during startup.

cloudoll support loading configurations based on the environment, defining configuration files for multiple environments

```ini
config
|- conf.local.yaml
|- conf.prod.yaml
`- conf.test.yaml
```

now, we create a config file:
```sh
$ mkdir -p config/conf.local.yaml
$ vi config/conf.local.yaml
```

the flollowing is mysql and server's configuration:
```yaml
server:
  host: 192.168.0.1
  port: 9001
  static: false
  client_max_size: 1024000
  static: 
    prefix: /static
    show_index: true
    append_version: true
    follow_symlinks: true
database:
  mysql:
    host: 127.0.0.1
    port: 3306
    user: root
    password: abcd
    db: blog
    charset: utf8mb4
```
the `local` will be used as default configuration, when you start your application, it will load the `local` configuration. like `cloudoll start -n myapp -env local` will load the `conf.local.yaml` configuration.

# cli 

## Create model

export model from database
```sh
cloudoll gen -t users 
```
More parameters:
- -p (--path) the path to save the model
- -c (--create) to create model or create tables, default is create model
- -t (--table) The model or table name to be generated, separated by `,`, `ALL` for all tables
- -env (--environment) to load the configuration file , default is `local`
- -db (--database) Database instance name, depends on the configuration file, if there are multiple databases
- -h (--help) help

## Development and debugging

```sh
cloudoll start --name myapp -env local -m development
```

## Production Environment

```sh
cloudoll start --name myapp -env prod --mode production
```

you can use `clodoll stop myapp` to stop your application ,
or use `cloudoll restart myapp` to restart your application.
`cloudoll list` to see all your applications.
