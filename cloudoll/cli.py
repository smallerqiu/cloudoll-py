import click
from .web.settings import get_config
from .orm.mysql import Mysql
from .orm.postgres import Postgres
from .utils.m2d import create_models, create_tables
import asyncio
import os
import sys
from .logging import error
import traceback
from cloudoll.web import app
import importlib
from pathlib import Path
from . import __version__
import traceback
import logging
from .utils.watch import AppTask, Config


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="cloudoll")
def cli() -> None:
    pass


life_cycle = ['on_startup', 'on_shutdown', 'on_cleanup', 'cleanup_ctx']


@cli.command()
@click.option('-p', '--path', help="Model's relative path,save models or create tables", default="models.py")
@click.option('-c', '--create', help='For create model or table, model / table', default='model')
@click.option('-t', '--table', help="Table's name or Model's name, split by `,` or 'ALL'", required=True)
@click.option('-env', '--environment', help="Environment, local / test / prod", default="local")
@click.option('-db', '--database', help="Database name, pick the database in conf.{env}.yaml", default='mysql')
def gen(path, create, table, environment, database) -> None:
    """Help to create models or tables."""
    # click.echo(create)
    async def start():
        try:
            config = get_config(environment)
            url_config = config.get('database')
            if url_config is None:
                raise ValueError(
                    f"Can't find the database config in conf.{environment}.yaml")
            db_config = url_config.get(database)
            if db_config is None:
                raise ValueError(
                    f"Can't find the database config key ->{database} in conf.{environment}.yaml")
            sa = await Mysql().create_engine(**db_config)
            if sa.pool is None:
                return
            model_path = os.path.join(os.path.abspath("."), path)
            # print(model_path)
            tables = None
            if table != 'ALL':
                tables = table.split(',')

            if create == 'model':
                await create_models(sa, path, tables=tables)
                print(f'Model save at:{model_path}')
            elif create == 'table':
                if model_path is None:
                    raise ValueError("Need package name or model name.")
                await create_tables(sa, model_path, tables=tables)

        except Exception as e:
            error(e)
            print(traceback.print_exc())
            click.echo('input `cloudoll --help` for more helps.')
        finally:
            await sa.close()

    asyncio.run(start())


@cli.command()
@click.option('-env', '--environment', help="Environment, local / test / prod", default="local")
@click.option('-p', '--port', help="Server's port", default=None)
@click.option('-h', '--host', help="Server's host", default=None)
@click.option('-path', '--path', help="Unix file system path to serve on. Specifying a path will cause hostname and port arguments to be ignored.")
@click.option('-m', '--model', help="Entry point model name. delfault name app", default='app')
def start(environment, host, port, path, model) -> None:
    """Start a services."""
    try:
        sys.path.append('.')
        entry = importlib.import_module(model)

        App = app.create(env=environment)
        for cycle in life_cycle:
            if hasattr(entry, cycle):
                cy = getattr(App, cycle)
                cy.append(getattr(entry, cycle))
        config = Config(host=host, port=port, path=path, env=environment)
        task = AppTask(Path('.').resolve(), config)
        App.cleanup_ctx.append(task.cleanup_ctx)
        App.run(host=host, port=port, path=path)
    except Exception as e:
        error(e)
        print(traceback.format_exc())
        sys.exit(2)


_project_existing = click.Path(dir_okay=True)


@cli.command()
@click.argument('project-name', type=_project_existing, required=True)
def create(project_name) -> None:
    full_path = os.path.join(os.path.abspath('.'), project_name)
    # log = logging.getLogger('cloudoll.create')
    if os.path.exists(full_path):
        logging.exception(f'Project name `{project_name}` already exist.')
        # return None


if __name__ == '__main__':
    cli()
