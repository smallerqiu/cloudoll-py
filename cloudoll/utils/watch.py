from typing import AsyncIterator, Iterable, Optional, Tuple, Union
from pathlib import Path
from ..web import Application, app
import asyncio
import os
import signal
import sys
from multiprocessing import Process
from watchfiles import awatch, DefaultFilter
from ..logging import debug, info, warning, exception
import contextlib
from typing import Any, Iterator, Optional, NoReturn
from typing import TYPE_CHECKING, Optional, Sequence, Union


class CloudollFilter(DefaultFilter):

    def __init__(self, ignore_dirs: tuple = None) -> None:
        self.ignore_dirs = self.ignore_dirs+('logs')
        if ignore_dirs:
            self.ignore_dirs = self.ignore_dirs+ignore_dirs

        super().__init__()


class WatchTask:
    _app: Application
    _task: "asyncio.Task[None]"

    def __init__(self, path: Union[Path, str]):
        self._path = path

    async def start(self, app: Application) -> None:
        self._app = app
        self.stopper = asyncio.Event()
        ignore_dirs = app.config.get('ignore_dirs') or []
        self._awatch = awatch(
            self._path, stop_event=self.stopper, watch_filter=CloudollFilter(tuple(ignore_dirs)))
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        raise NotImplementedError()

    async def close(self) -> None:
        if self._task:
            self.stopper.set()
            if self._task.done():
                self._task.result()
            self._task.cancel()

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


class Config:
    def __init__(self, host, port, path, env, entry):
        self.host = host
        self.port: int = port
        self.path = path
        self.env = env
        self.entry = entry


def mian_app(tty_path, config: Config):
    with set_tty(tty_path):
        # app.create(env=config.env).run(**config.__dict__)
        # with asyncio.Runner() as runner:
        App = app.create(config.env, config.entry)
        try:
            App.run(**config.__dict__)
        except KeyboardInterrupt:
            pass
        # finally:
        #     with contextlib.suppress(asyncio.TimeoutError, KeyboardInterrupt):
        #         runner.run(App.app.cleanup())


class AppTask(WatchTask):

    def __init__(self, watch_path: str, config: Config):
        self._config = config
        self._reloads = 0
        assert watch_path
        super().__init__(watch_path)

    async def _run(self) -> None:
        assert self._app is not None
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
            # exception(exc)
            raise Exception('error running dev server')

    def _start_dev_server(self) -> None:
        act = 'Start' if self._reloads == 0 else 'Restart'
        info(f'{act}ing dev server')

        try:
            tty_path = os.ttyname(sys.stdin.fileno())
        except OSError:  # pragma: no branch
            # fileno() always fails with pytest
            tty_path = '/dev/tty'
        except AttributeError:
            # on windows, without a windows machine I've no idea what else to do here
            tty_path = None

        self._process = Process(target=mian_app,
                                args=(tty_path, self._config))
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

    async def close(self) -> None:
        self.stopper.set()
        await self._stop_dev_server()
        await asyncio.gather(super().close())
