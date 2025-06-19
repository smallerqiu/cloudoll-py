from pathlib import Path
import click
import asyncio
import os
import sys
from cloudoll.logging import error
from cloudoll import __version__
from typing import Any
from cloudoll.clitool.cli_main import run_app, run_gen, create_project
from cloudoll.clitool.process import ProcessManager


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="cloudoll")
def cli() -> None:
    pass


life_cycle = ["on_startup", "on_shutdown", "on_cleanup", "cleanup_ctx"]


@cli.command()
@click.option(
    "-p",
    "--path",
    help="Model's relative path,save models or create tables",
    default="models.py",
)
@click.option(
    "-c", "--create", help="For create model or table, model / table", default="model"
)
@click.option(
    "-t",
    "--table",
    help="Table's name or Model's name, split by `,` or 'ALL'",
    required=True,
)
@click.option(
    "-env", "--environment", help="Environment, local / test / prod", default="local"
)
@click.option(
    "-db",
    "--database",
    help="Database name, pick the database in conf.{env}.yaml",
    default="mysql",
)
def gen(**config: Any) -> None:
    """Help to create models or tables."""

    # click.echo(create)
    async def start():
        try:
            await run_gen(**config)
        except Exception as e:
            # traceback.print_exc()
            error("Error: %s", e)
            click.echo("input `cloudoll --help` for more helps.")
            sys.exit(2)

    asyncio.run(start())


@cli.command()
@click.option(
    "-env", "--environment", help="Environment, local / test / prod", default="local"
)
@click.option("-p", "--port", help="Server's port", default=None)
@click.option("-h", "--host", help="Server's host", default=None)
@click.option(
    "-m", "--mode", help="development or production mode", default="development"
)
@click.option(
    "-path",
    "--path",
    help="Unix file system path to serve on. Specifying a path will cause hostname and port arguments to be ignored.",
)
@click.option(
    "-n",
    "--name",
    help="Your service name",
    required=True,
)
@click.option(
    "-e", "--entry", help="Entry point model name. delfault name app", default="app"
)
def start(**config: Any) -> None:
    """Start a service."""
    try:
        active_config = {k: v for k, v in config.items() if v is not None}
        run_app(**active_config)
    except Exception as e:
        error(f"Error: {e}")
        # traceback.format_exc()
        sys.exit(2)


@cli.command()
@click.option(
    "-n",
    "--name",
    help="Your service name.",
    required=True,
)
def stop(name):
    """Stop a service."""
    ProcessManager.safe_exit(name)


@cli.command()
@click.option(
    "-n",
    "--name",
    help="Your service name",
    required=True,
)
@click.option(
    "-f",
    "--force",
    help="Force restart even if the service is not running",
    required=False,
)
def restart(name, force):
    """Restart a service."""
    pid = ProcessManager.get_running_pid(name)
    if not pid:
        click.echo("⚠️  Cloudoll server not running.")
        if not force:
            click.echo(f"⚠️  Service {name} not running，use --force to force restart")
            return

    ProcessManager.safe_exit(name)

    args = ProcessManager.load_start_args(name)
    if not args:
        click.echo(
            "❌ Can't find historical startup parameters, you can add --force option",
            err=True,
        )
        raise click.Abort()
    os.execvp(sys.executable, [sys.executable, sys.argv[0], *args])


@cli.command()
def list():
    """List all services."""
    ProcessManager.list()


@cli.command()
@click.argument("project-name", type=click.Path(dir_okay=True), required=True)
def create(project_name) -> None:
    create_project(project_name)


if __name__ == "__main__":
    cli()
