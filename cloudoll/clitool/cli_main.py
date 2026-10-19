import os
import re
import secrets
import shutil
import sys
import threading
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path
from typing import Any

from aiohttp import web

from cloudoll import __version__
from cloudoll.clitool.m2d import create_models, create_tables
from cloudoll.clitool.process import ProcessManager
from cloudoll.clitool.spinner import spinner_running
from cloudoll.clitool.watch import AppTask, run_supervisor
from cloudoll.logging import error, info, warning
from cloudoll.orm import create_engine
from cloudoll.utils.common import Object, chainMap
from cloudoll.web import app
from cloudoll.web.settings import get_config


def run_app(**config_kwargs: Any) -> None:
    config = Object(config_kwargs)
    info(
        "Starting Cloudoll %s | mode=%s env=%s root=%s PID=%s",
        __version__,
        config.mode,
        config.environment,
        Path.cwd(),
        os.getpid(),
    )
    app_config = get_config(config.environment)
    # print(environment, host, port, mode, path, entry)
    # return
    if config.mode == "production":
        ProcessManager.ensure_runtime_dir()
        # ProcessManager.cleanup(config.name)

        with ProcessManager.service_lock(config.name):
            pid = ProcessManager.get_running_pid(config.name)
            if pid:
                error(f"⚠️  {config.name} is already running with PID {pid}. Exiting.")
                return
            ProcessManager.save_start_args(config.name, sys.argv[1:])
            try:
                App = app.current().create(
                    env=config.environment, config=app_config, entry_model=config.entry
                )
                ProcessManager.save_pid(config.name, os.getpid())
                App.run(
                    **{
                        k: config[k]
                        for k in ("host", "port", "path")
                        if config.get(k) is not None
                    }
                )
            finally:
                ProcessManager.cleanup(config.name)
    else:
        supervisor_app = web.Application()
        defaults = {"host": "127.0.0.1", "port": 9001, "path": None}
        conf_server = app_config.get("server", {})
        env_server = {"host": config.host, "port": config.port, "path": config.path}
        server = chainMap(defaults, conf_server, env_server)
        app_config["server"] = server
        task = AppTask(
            Path(".").resolve(), app_config, entry=config.entry, env=config.environment
        )
        supervisor_app.cleanup_ctx.append(task.cleanup_ctx)
        run_supervisor(supervisor_app)
        if task.failure is not None:
            raise RuntimeError(
                "Development server supervision failed"
            ) from task.failure


async def run_gen(**config_kwargs: Any) -> None:
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
    try:
        model_path = Path(config.path)
        tables = None
        if config.table and config.table.upper() != "ALL":
            tables = [
                table.strip() for table in config.table.split(",") if table.strip()
            ]
        if config.create == "model":
            await create_models(sa, config.path, tables=tables)
            info(f"Model save at:{model_path}")
        elif config.create == "table":
            await create_tables(sa, model_path, tables=tables)
        else:
            raise ValueError("create must be 'model' or 'table'")
    finally:
        await sa.close()


# The template is imported to be copied, so its own __pycache__ sits next to the
# files an application is supposed to receive; the same goes for anything a
# developer ran inside the template directory.
_BUILD_ARTIFACTS = re.compile(r"^(__pycache__|.*\.py[co])$")
# A project name reaches the shell in the printed start hint, the pid file and the
# service name, so it is limited to characters that need no quoting.
_PROJECT_NAME = re.compile(r"\w[\w.\-]*")


def _is_build_artifact(name: str) -> bool:
    return bool(_BUILD_ARTIFACTS.match(name))


def _skip_build_artifacts(_directory: str, contents: Iterable[str]) -> set[str]:
    return {name for name in contents if _is_build_artifact(name)}


def create_project(project_name: str) -> None:
    """
    Create a new Cloudoll project with the specified name.

    A name that is not a plain directory name, an existing target and a failed
    copy all raise; the `cloudoll create` command turns that into a non-zero exit
    so a script can tell a new project from nothing.
    """
    project_dir = Path(project_name)
    # The last component is what the printed `cloudoll start -n <name>` hint and
    # the pid file are built from, so it has to survive a shell unquoted.
    if not _PROJECT_NAME.fullmatch(project_dir.name or project_name):
        raise ValueError(
            f"Project name `{project_name}` must end with letters, digits, "
            "underscore, dot or dash; spaces and shell characters are refused."
        )
    if project_dir.exists():
        raise FileExistsError(f"Project `{project_name}` already exists.")
    project_dir.mkdir(parents=True)

    stop = {"stop": False}
    t = threading.Thread(target=spinner_running, args=(stop,))
    t.start()
    try:
        from cloudoll import template

        template_path = files(template)
        for item in template_path.iterdir():
            if _is_build_artifact(item.name):
                continue
            dst = project_dir / item.name
            if item.is_dir():
                shutil.copytree(str(item), dst, ignore=_skip_build_artifacts)
            else:
                shutil.copy2(str(item), dst)
        # The YAML keeps its $CLOUDOLL_JWT_SECRET and $CLOUDOLL_SESSION_SECRET
        # placeholders so both keys stay injectable by shell, container or process
        # manager. EnvYAML reads a .env from the working directory, so the fresh
        # local keys live there instead, and the project's .gitignore keeps that
        # file out of version control.
        (project_dir / ".env").write_text(
            "CLOUDOLL_JWT_SECRET=%s\nCLOUDOLL_SESSION_SECRET=%s\n"
            % (secrets.token_urlsafe(48), secrets.token_urlsafe(48)),
            encoding="utf-8",
        )
        (project_dir / ".env.example").write_text(
            "CLOUDOLL_JWT_SECRET=replace-with-an-independent-high-strength-secret\n"
            "CLOUDOLL_SESSION_SECRET=replace-with-an-independent-high-strength-secret\n",
            encoding="utf-8",
        )
        if not (project_dir / ".gitignore").is_file():
            warning(
                "The project has no .gitignore; keep `.env` out of version control."
            )
        from cloudoll.ai.commands import initialize_project

        initialize_project(project_dir)
    except BaseException:
        # Only this call created the directory, so a half-written project - no
        # config, no AI assets - is safe to remove and worse to leave behind.
        shutil.rmtree(project_dir, ignore_errors=True)
        raise
    finally:
        stop["stop"] = True
        t.join()

    info(f"Project `{project_dir}` created successfully at {project_dir.resolve()}.")
    info(
        "Run `cd %s && cloudoll start -n %s` to start your project.",
        project_name,
        project_dir.name,
    )
