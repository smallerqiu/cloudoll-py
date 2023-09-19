import click
from .web.settings import get_config
from .orm.mysql import Mysql
from .orm.postgres import Postgres
from .utils.m2d import create_models
import asyncio
import os
from .logging import error


@click.command()
@click.option('-p', '--path', help='create model path or from model to create table', default="models.py")
@click.option('-c', '--create', help='For create model or table, model / table', default='model')
@click.option('-t', '--table', help="Table's name or Model's name, split by `,` or 'ALL'", required=True)
@click.option('-env', '--environment', help="Environment, local / test / prod", default="local")
@click.option('-db', '--database', help="Database name, pick the database in conf.{env}.yaml", default='mysql')
def main(path, create,  table, environment, database):
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
            pool = await Mysql().create_engine(**db_config)
            if create == 'model':
                if table == 'ALL':
                    await create_models(pool, path, None)
                else:
                    tbs = table.split(',')
                    await create_models(pool, path, tables=tbs)
                save_path = os.path.join(os.path.abspath("."), path)
                print(save_path)
            elif create == 'talbe':
                pass

        except Exception as e:
            error(e)
            click.echo('input `cloudoll --help` for more helps.')
        finally:
            await pool.close()

    asyncio.run(start())


if __name__ == '__main__':
    main()
