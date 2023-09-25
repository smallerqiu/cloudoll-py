from typing import AsyncIterator, Iterable, Optional, Tuple, Union
from pathlib import Path
from ..web import Application
import asyncio
import os
import signal
import sys
from multiprocessing import Process
from watchfiles import awatch
from ..logging import debug, info, warning, exception
from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError, ClientConnectionError

class WatchTask:
    _app: Application
    _task: "asyncio.Task[None]"

    def __init__(self, path: Union[Path, str]):
        self._path = path

    async def start(self, app: Application) -> None:
        self._app = app
        self.stopper = asyncio.Event()
        self._awatch = awatch(self._path, stop_event=self.stopper)
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        raise NotImplementedError()

    async def close(self, *args: object) -> None:
        if self._task:
            self.stopper.set()
            if self._task.done():
                self._task.result()
            self._task.cancel()

    async def cleanup_ctx(self, app: Application) -> AsyncIterator[None]:
        await self.start(app)
        yield
        await self.close(app)


class AppTask(WatchTask):

    def __init__(self, config: Config):
        self._config = config
        self._reloads = 0
        self._session: Optional[ClientSession] = None
        self._runner = None
        assert self._config.watch_path
        super().__init__(self._config.watch_path)

    async def _run(self) -> None:
        assert self._app is not None

        self._session = ClientSession()
        try:
            self._start_dev_server()

            async for changes in self._awatch:
                self._reloads += 1
                if any(f.endswith('.py') for _, f in changes):
                    debug('%d changes, restarting server', len(changes))
                    await self._stop_dev_server()
                    self._start_dev_server()
                    await asyncio.sleep(1)
        except Exception as exc:
            exception(exc)
            await self._session.close()
            raise Exception('error running dev server')


    def _start_dev_server(self) -> None:
        act = 'Start' if self._reloads == 0 else 'Restart'
        info('%sing dev server at http://%s:%s ●', act,
             self._config.host, self._config.main_port)

        try:
            tty_path = os.ttyname(sys.stdin.fileno())
        except OSError:  # pragma: no branch
            # fileno() always fails with pytest
            tty_path = '/dev/tty'
        except AttributeError:
            # on windows, without a windows machine I've no idea what else to do here
            tty_path = None

        self._process = Process(target=serve_main_app,
                                args=(self._config, tty_path))
        self._process.start()

    async def _stop_dev_server(self) -> None:
        if self._process.is_alive():
            debug('stopping server process...')
            if self._process.pid:
                debug("sending SIGINT")
                os.kill(self._process.pid, signal.SIGINT)
            self._process.join(5)
            if self._process.exitcode is None:
                warning('process has not terminated, sending SIGKILL')
                self._process.kill()
                self._process.join(1)
            else:
                debug('process stopped')
        else:
            warning(
                'server process already dead, exit code: %s', self._process.exitcode)

    async def close(self, *args: object) -> None:
        self.stopper.set()
        await self._stop_dev_server()
        if self._session is None:
            raise RuntimeError(
                "Object not started correctly before calling .close()")
        await asyncio.gather(super().close(), self._session.close())
