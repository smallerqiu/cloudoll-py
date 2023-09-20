import click
from .web.settings import get_config
from .orm.mysql import Mysql
from .orm.postgres import Postgres
from .utils.m2d import create_models,create_tables
import asyncio
import os
from .logging import error

@click.command()
@click.option('-p', '--path', help="Model's relative path,save models or create tables", default="models.py")
@click.option('-c', '--create', help='For create model or table, model / table', default='model')
@click.option('-t', '--table', help="Table's name or Model's name, split by `,` or 'ALL'", required=True)
@click.option('-env', '--environment', help="Environment, local / test / prod", default="local")
@click.option('-db', '--database', help="Database name, pick the database in conf.{env}.yaml", default='mysql')
def main(path, create, table, environment, database):
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
            click.echo('input `cloudoll --help` for more helps.')
        finally:
            await sa.close()

    asyncio.run(start())


if __name__ == '__main__':
    main()
