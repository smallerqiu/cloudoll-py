import click
import asyncio
import os
import sys
from .logging import print_error
from . import __version__
from typing import Any
from .utils.cli_main import run_app, run_gen
sys.path.append(os.path.abspath("."))


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="cloudoll")
def cli() -> None:
    pass


life_cycle = ["on_startup", "on_shutdown", "on_cleanup", "cleanup_ctx"]


@cli.command()
@click.option("-p", "--path", help="Model's relative path,save models or create tables", default="models.py",)
@click.option("-c", "--create", help="For create model or table, model / table", default="model")
@click.option("-t", "--table", help="Table's name or Model's name, split by `,` or 'ALL'", required=True,)
@click.option("-env", "--environment", help="Environment, local / test / prod", default="local")
@click.option("-db", "--database", help="Database name, pick the database in conf.{env}.yaml", default="mysql",)
def gen(**config: Any) -> None:
    """Help to create models or tables."""

    # click.echo(create)
    async def start():
        try:
            sa = await run_gen(**config)
        except Exception as e:
            # traceback.print_exc()
            print_error('Error: %s', e)
            click.echo("input `cloudoll --help` for more helps.")
        finally:
            await sa.close()

    asyncio.run(start())


@cli.command()
@click.option("-env", "--environment", help="Environment, local / test / prod", default="local")
@click.option("-p", "--port", help="Server's port", default=None)
@click.option("-h", "--host", help="Server's host", default=None)
@click.option("-m", "--mode", help="development or production mode", default='development')
@click.option("-path", "--path", help="Unix file system path to serve on. Specifying a path will cause hostname and port arguments to be ignored.",)
@click.option("-e", "--entry", help="Entry point model name. delfault name app", default="app")
def start(**config: Any) -> None:
    """Start a services."""
    try:
        active_config = {k: v for k, v in config.items() if v is not None}
        run_app(**active_config)
    except Exception as e:
        print_error('Error: %s', e)
        # traceback.format_exc()
        sys.exit(2)


_project_existing = click.Path(dir_okay=True)


@cli.command()
@click.argument("project-name", type=_project_existing, required=True)
def create(project_name) -> None:
    full_path = os.path.join(os.path.abspath("."), project_name)
    # log = logging.getLogger('cloudoll.create')
    if os.path.exists(full_path):
        print_error(f"Project name `{project_name}` already exist.")
        # return None


if __name__ == "__main__":
    cli()
