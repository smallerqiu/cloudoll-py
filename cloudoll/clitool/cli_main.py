from typing import Any
from cloudoll.web.settings import get_config
from cloudoll.logging import info, error
from cloudoll.utils.common import Object, chainMap
from cloudoll.clitool.watch import AppTask
from aiohttp import web
from cloudoll.web import app
from pathlib import Path
from cloudoll.clitool.m2d import create_models, create_tables
from cloudoll.orm import create_engine
import os
from cloudoll.clitool.process import ProcessManager
import sys
from importlib.resources import files
import shutil
from cloudoll.clitool.spinner import spinner_running
import threading


def run_app(**config_kwargs: Any):
    config = Object(config_kwargs)
    info("current mode: %s", config.mode)
    app_config = get_config(config.environment)
    # print(environment, host, port, mode, path, entry)
    # return
    if config.mode == "production":
        ProcessManager.ensure_runtime_dir()
        ProcessManager.save_start_args(config.name, sys.argv[1:])
        # ProcessManager.cleanup(config.name)

        pid = ProcessManager.get_running_pid(config.name)
        if pid:
            error(f"⚠️  {config.name} is already running with PID {pid}. Exiting.")
            return
        ProcessManager.register_signal_handlers(config.name)
        try:
            App = app.create(
                env=config.environment, config=app_config, entry_model=config.entry
            )
            ProcessManager.save_pid(config.name, os.getpid())
            App.run()
        finally:
            ProcessManager.cleanup(config.name)
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
        task = AppTask(
            Path(".").resolve(), app_config, entry=config.entry, env=config.environment
        )
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
    model_path = Path(config.path)
    tables = None
    if config.table and config.table != "ALL":
        tables = config.table.split(",")
    if tables is None:
        return
    if config.create == "model":
        await create_models(sa, config.path, tables=tables)
        info(f"Model save at:{model_path}")
    elif config.create == "table":
        if model_path is None:
            raise ValueError("Need package name or model name.")
        await create_tables(sa, model_path, tables=tables)
    return sa


def create_project(project_name: str) -> None:
    """
    Create a new Cloudoll project with the specified name.
    """
    project_dir = Path(project_name)
    if project_dir.exists():
        error(f"Project name `{project_name}` already exist.")
        return
    else:
        project_dir.mkdir(parents=True)

    stop = {"stop": False}
    t = threading.Thread(target=spinner_running, args=(stop,))
    t.start()
    try:
        from cloudoll import template

        template_path = files(template)
        # shutil.copytree(template_path, project_dir, dirs_exist_ok=True)
        for item in template_path.iterdir():
            dst = project_dir / item.name
            if item.is_dir():
                shutil.copytree(str(item), dst)
            else:
                shutil.copy2(str(item), dst)
    finally:
        stop["stop"] = True
        t.join()

    info(f"Project `{project_name}` created successfully at {project_dir.resolve()}.")
    info(
        "Run `cd %s && cloudoll start -n %s` to start your project.",
        project_name,
        project_name,
    )
