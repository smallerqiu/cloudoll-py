"""Smoke-test the actual wheel outside the source checkout (no DB needed)."""

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    wheel = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="cloudoll-wheel-") as directory:
        root = Path(directory)
        installed = root / "installed"
        with zipfile.ZipFile(wheel) as archive:
            assert "cloudoll/py.typed" in archive.namelist()
            for required in (
                "config/conf.local.yaml",
                "controllers/home/index.py",
                "controllers/api/index.py",
                "middlewares/auth.py",
                "templates/index.html",
                "static/img/cat.avif",
            ):
                assert "cloudoll/template/" + required in archive.namelist(), required
            archive.extractall(installed)
        logs = root / "logs"
        logs.mkdir()
        env = dict(os.environ, PYTHONPATH=str(installed), CLOUDOLL_LOG_DIR=str(logs))
        subprocess.run(
            [
                sys.executable,
                "-c",
                """
import asyncio
import os
import sys
import importlib.abc
from pathlib import Path

class NoOptionalDrivers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"redis", "aiomcache", "aiomysql", "aiopg", "aws_advanced_python_wrapper"}:
            raise ModuleNotFoundError("Optional driver unavailable: " + fullname)

sys.meta_path.insert(0, NoOptionalDrivers())
import cloudoll
from cloudoll.orm import Query
from cloudoll.orm.model import Model

class TypedRow(Model):
    pass

assert isinstance(TypedRow.use(None), Query)
from cloudoll.clitool.cli_main import create_project
from cloudoll.web import Application
from aiohttp.test_utils import TestClient, TestServer

assert Path(cloudoll.__file__).resolve().is_relative_to(Path("installed").resolve()), cloudoll.__file__
create_project("sample")
os.chdir("sample")

async def verify():
    application = Application().create(entry_model=None)
    async with TestClient(TestServer(application.app)) as client:
        response = await client.get("/")
        assert response.status == 200, await response.text()
        assert "cloudoll" in await response.text()
        response = await client.get("/static/css/index.css")
        assert response.status == 200
        response = await client.get("/api/test?example=yes")
        assert response.status == 200, await response.text()
        assert (await response.json())["data"]["example"] == "yes"

asyncio.run(verify())
print("Wheel scaffold, configuration, HTTP routes, templates and static assets: OK")
""",
            ],
            cwd=root,
            env=env,
            check=True,
        )


if __name__ == "__main__":
    main()
