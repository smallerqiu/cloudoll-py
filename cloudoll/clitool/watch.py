from typing import AsyncIterator, Optional, Union
from pathlib import Path
from cloudoll.web import Application, app
import asyncio
import os
import signal
import sys
from contextlib import suppress
from multiprocessing import Process
from watchfiles import awatch, DefaultFilter
from cloudoll.logging import info, warning, error, debug
import contextlib
from typing import Iterator, Optional
from typing import Optional, Union
from aiohttp import web
import traceback
from cloudoll.utils.common import check_port_open


class CloudollFilter(DefaultFilter):
    def __init__(self, ignore_dirs: tuple = ()) -> None:
        self.ignore_dirs = self.ignore_dirs + tuple("logs")
        if ignore_dirs:
            self.ignore_dirs = self.ignore_dirs + ignore_dirs

        super().__init__()


class WatchTask:
    _app: Application
    _task: "asyncio.Task[None]"

    def __init__(self, path: Union[Path, str]):
        self._path = path

    async def start(self, app: Application) -> None:
        self._app = app
        self.stopper = asyncio.Event()
        ignore_dirs = self._config["server"].get("ignore_dirs", [])
        self._awatch = awatch(
            self._path,
            stop_event=self.stopper,
            watch_filter=CloudollFilter(tuple(ignore_dirs)),
        )
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        raise NotImplementedError()

    async def close(self, *args) -> None:
        if self._task:
            self.stopper.set()
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def cleanup_ctx(self, app: Application) -> AsyncIterator[None]:
        await self.start(app)
        yield
        await self.close()


@contextlib.contextmanager
def set_tty(tty_path: Optional[str]) -> Iterator[None]:
    try:
        if not tty_path:
            # to match OSError from open
            raise OSError()
        with open(tty_path) as tty:
            sys.stdin = tty
            yield
    except OSError:
        # either tty_path is None (windows) or opening it fails (eg. on pycharm)
        yield


def mian_app(tty_path, config, entry, env):
    with set_tty(tty_path):
        if sys.version_info >= (3, 11):
            with asyncio.Runner() as runner:
                app_runner = runner.run(create_main_app(config, entry, env))
                try:
                    runner.run(
                        start_main_app(
                            app_runner,
                            config["server"]["host"],
                            config["server"]["port"],
                        )
                    )
                    runner.get_loop().run_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    with suppress(asyncio.TimeoutError, KeyboardInterrupt):
                        runner.run(app_runner.cleanup())
        else:
            loop = asyncio.new_event_loop()
            runner = loop.run_until_complete(create_main_app(config, entry, env))
            try:
                loop.run_until_complete(
                    start_main_app(
                        runner, config["server"]["host"], config["server"]["port"]
                    )
                )
                loop.run_forever()
            except KeyboardInterrupt:
                pass
            finally:
                with suppress(asyncio.TimeoutError, KeyboardInterrupt):
                    loop.run_until_complete(runner.cleanup())


async def create_main_app(config, entry, env):
    await check_port_open(config["server"]["port"])
    App = app.create(env=env, config=config, entry_model=entry)
    return web.AppRunner(App.app, shutdown_timeout=0.1)


async def start_main_app(runner, host, port):
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    info(f"Server running on http://{host}:{port}")
    info("(Press CTRL+C to quit)")
    await site.start()


class AppTask(WatchTask):
    def __init__(self, watch_path: str, config, entry: None, env: str):
        self._config = config
        self._entry = entry
        self._env = env
        self._reloads = 0
        assert watch_path
        super().__init__(watch_path)

    async def _run(self) -> None:
        assert self._app is not None
        self._start_dev_server()
        try:
            async for changes in self._awatch:
                self._reloads += 1
                if any(f.endswith(".py") for _, f in changes):
                    info(f"{len(changes)} changes, restarting server")
                    await self._stop_dev_server()
                    self._start_dev_server()
                    await asyncio.sleep(1)
        except Exception as exc:
            traceback.print_exc()

            raise Exception("error running dev server")

    def _start_dev_server(self) -> None:
        act = "Start" if self._reloads == 0 else "Restart"
        info(f"{act}ing dev server")

        try:
            tty_path = os.ttyname(sys.stdin.fileno())
        except OSError:  # pragma: no branch
            # fileno() always fails with pytest
            tty_path = "/dev/tty"
        except AttributeError:
            # on windows, without a windows machine I've no idea what else to do here
            tty_path = None

        # for key, value in self._config.items():
        #     try:
        #         pickle.dumps(value)
        #     except Exception as e:
        #         print(f"Serialization error on key '{key}': {e} {value}")

        # import pickle
        # try:
        #     pickle.dumps(b)  # 检查是否可序列化
        # except Exception as e:
        #     print("Serialization error:", e)
        try:
            self._process = Process(
                target=mian_app, args=(tty_path, self._config, self._entry, self._env)
            )
            self._process.start()
        except Exception as e:
            error(f"Error starting server: {e}")

    async def _stop_dev_server(self) -> None:
        if self._process.is_alive():
            info("stopping server process...")
            # if self._process.pid:
            #     info("sending SIGINT")
            #     os.kill(self._process.pid, signal.SIGINT)
            self._process.terminate()
            self._process.join(5)
            if self._process.exitcode is None:
                warning("process has not terminated, sending SIGKILL")
                self._process.kill()
                self._process.join(1)
            else:
                info("process stopped")
        else:
            warning(
                "server process already dead, exit code: %s", self._process.exitcode
            )

    async def close(self, *args) -> None:
        self.stopper.set()
        await self._stop_dev_server()
        await asyncio.gather(super().close(*args))
