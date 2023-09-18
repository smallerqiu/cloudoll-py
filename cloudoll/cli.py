import click
from .web.settings import get_config
from .orm.mysql import Mysql
from .orm.postgres import Postgres
from .utils.m2d import create_models
import asyncio
from .logging import error


@click.command()
@click.option('-p', '--path', help='create model path or from model to creat table', default="models.py")
@click.option('-c', '--create', help='For create model or table, model | table', default='model')
@click.option('-t', '--table', help="Table's name or Model's name, split by `,` or 'ALL'")
@click.option('-env', '--environment', help="Environment, local | test | prod", default="local")
@click.option('-db', '--database', help="Database name, pick the database in conf.{env}.yaml", default='mysql')
def main(path, create,  table, environment, database):
    """Help to create models or tables."""
    # click.echo(create)
    async def start():
        try:
            config = get_config(environment)
            url_config = config.get('database')
            # print(url_config, environment)
            if url_config is None:
                raise ValueError(
                    f"Can't find the database config in conf.{environment}.yaml")
            db_config = url_config.get(database)
            if db_config is None:
                raise ValueError(
                    f"Can't find the database config key ->{database} in conf.{environment}.yaml")
            print(db_config)
            pool = await Mysql().create_engine(**db_config)
            if table is None:
                raise ValueError(
                    f"")
            if create=='model':
                
            elif create=='talbe':
                pass
        except Exception as e:
            error(e)
            click.echo('input `cloudoll --help` for more helps.')
    asyncio.run(start())


if __name__ == '__main__':
    main()
