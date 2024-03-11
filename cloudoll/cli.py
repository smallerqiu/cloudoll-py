import click
from .web.settings import get_config
from .web import app
from .orm import create_engine
from .utils.m2d import create_models, create_tables
import asyncio
import os
import sys
from .logging import error, print_info
from pathlib import Path
from . import __version__
import traceback
import logging
from .utils.watch import AppTask
from aiohttp import web
from .utils.common import chainMap

sys.path.append(os.path.abspath("."))


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="cloudoll")
def cli() -> None:
    pass


life_cycle = ["on_startup", "on_shutdown", "on_cleanup", "cleanup_ctx"]


@cli.command()
@click.option("-p", "--path",help="Model's relative path,save models or create tables",default="models.py",)
@click.option("-c", "--create", help="For create model or table, model / table", default="model")
@click.option("-t", "--table",help="Table's name or Model's name, split by `,` or 'ALL'",required=True,)
@click.option("-env", "--environment", help="Environment, local / test / prod", default="local")
@click.option("-db", "--database",help="Database name, pick the database in conf.{env}.yaml",default="mysql",)
def gen(path, create, table, environment, database) -> None:
    """Help to create models or tables."""

    # click.echo(create)
    async def start():
        try:
            config = get_config(environment)
            url_config = config.get("database")
            if url_config is None:
                raise ValueError(
                    f"Can't find the database config in conf.{environment}.yaml"
                )
            db_config = url_config.get(database)
            if db_config is None:
                raise ValueError(
                    f"Can't find the database config key ->{database} in conf.{environment}.yaml"
                )
            sa = await create_engine(**db_config)
            if sa.pool is None:
                return
            model_path = os.path.join(os.path.abspath("."), path)
            # print(model_path)
            tables = None
            if table != "ALL":
                tables = table.split(",")

            if create == "model":
                await create_models(sa, path, tables=tables)
                print_info(f"Model save at:{model_path}")
            elif create == "table":
                if model_path is None:
                    raise ValueError("Need package name or model name.")
                await create_tables(sa, model_path, tables=tables)

        except Exception as e:
            error(e)
            print(traceback.print_exc())
            click.echo("input `cloudoll --help` for more helps.")
        finally:
            await sa.close()

    asyncio.run(start())


@cli.command()
@click.option("-env", "--environment", help="Environment, local / test / prod", default="local")
@click.option("-p", "--port", help="Server's port", default=None)
@click.option("-h", "--host", help="Server's host", default=None)
@click.option("-path", "--path",help="Unix file system path to serve on. Specifying a path will cause hostname and port arguments to be ignored.",)
@click.option("-m", "--model", help="Entry point model name. delfault name app", default="app")
def start(environment, host, port, path, model) -> None:
    """Start a services."""
    try:
        aux_app = web.Application(
            logger=None,
        )
        config = get_config(environment)
        server = config.get("server", {})
        server = chainMap(server, {"host": host, "port": port, "path": path})
        config["server"] = server

        aux_port = int(server.port) + 1
        task = AppTask(Path(".").resolve(), config, entry=model)
        aux_app.cleanup_ctx.append(task.cleanup_ctx)
        web.run_app(
            aux_app,
            access_log=None,
            host=host,
            port=aux_port,
            print=None,
            shutdown_timeout=0.1,
        )
    except Exception as e:
        error(e)
        print(traceback.format_exc())
        sys.exit(2)


_project_existing = click.Path(dir_okay=True)


@cli.command()
@click.argument("project-name", type=_project_existing, required=True)
def create(project_name) -> None:
    full_path = os.path.join(os.path.abspath("."), project_name)
    # log = logging.getLogger('cloudoll.create')
    if os.path.exists(full_path):
        logging.exception(f"Project name `{project_name}` already exist.")
        # return None


if __name__ == "__main__":
    cli()
