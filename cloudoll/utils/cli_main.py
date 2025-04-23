from typing import Any
from ..web.settings import get_config
from ..logging import print_info
from .common import Object, chainMap
from .watch import AppTask
from aiohttp import web
from ..web import app
from pathlib import Path
from .m2d import create_models, create_tables
from ..orm import create_engine
import os


def run_app(**config_kwargs: Any):
    config = Object(config_kwargs)
    print_info("Current mode: ", config.mode)
    app_config = get_config(config.environment)
    # print(environment, host, port, mode, path, entry)
    # return
    if config.mode == 'production':
        App = app.create(env=config.environment, config=app_config, entry_model=config.entry)
        App.run()
    else:
        aux_app = web.Application(
            logger=None,
        )
        defaults = {"host": "0.0.0.0", "port": 9001, "path": None}
        conf_server = app_config.get("server", {})
        env_server = {"host": config.host, "port": config.port, "path": config.path}
        server = chainMap(defaults, conf_server, env_server)
        app_config["server"] = server
        aux_port = int(server.port) + 1
        task = AppTask(Path(".").resolve(), app_config, entry=config.entry, env=config.environment)
        aux_app.cleanup_ctx.append(task.cleanup_ctx)
        web.run_app(
            aux_app,
            access_log=None,
            host=config.host,
            port=aux_port,
            print=None,
            shutdown_timeout=0.1,
        )


async def run_gen(**config_kwargs: Any):
    config = Object(config_kwargs)
    configs = get_config(config.environment)
    db_configs = configs.get("database")
    if db_configs is None:
        raise KeyError(
            f"Can't find the database config in conf.{config.environment}.yaml"
        )
    db_config = db_configs.get(config.database)
    if db_config is None:
        raise KeyError(
            f"Can't find the database config key ->{config.database} in conf.{config.environment}.yaml"
        )
    sa = await create_engine(**db_config)
    if sa.pool is None:
        return
    model_path = os.path.join(os.path.abspath("."), config.path)
    tables = None
    if config.table != "ALL":
        tables = config.table.split(",")

    if config.create == "model":
        await create_models(sa, config.path, tables=tables)
        print_info(f"Model save at:{model_path}")
    elif config.create == "table":
        if model_path is None:
            raise ValueError("Need package name or model name.")
        await create_tables(sa, model_path, tables=tables)
