"""Development server supervision with explicit startup and shutdown boundaries."""

import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncIterator, Iterator
from multiprocessing import Event, Pipe, Process
from pathlib import Path
from typing import Any, Optional, Union

from aiohttp import web
from watchfiles import DefaultFilter, awatch

from cloudoll.logging import info
from cloudoll.web import Application, app


class CloudollFilter(DefaultFilter):
    def __init__(self, ignore_dirs: tuple[str, ...] = ()) -> None:
        self.ignore_dirs = tuple(self.ignore_dirs) + ("logs",) + ignore_dirs
        super().__init__()


class WatchTask:
    _config: dict[str, Any]

    def __init__(self, path: Union[Path, str]) -> None:
        self._path = path
        self._task: Optional[asyncio.Task[None]] = None
        self._stopper: Optional[asyncio.Event] = None

    @property
    def stopper(self) -> asyncio.Event:
        # On Python 3.9 Event binds to a loop at construction. Defer until
        # startup/cleanup executes inside the supervisor's running loop.
        if self._stopper is None:
            self._stopper = asyncio.Event()
        return self._stopper

    async def start(self, application: web.Application) -> None:
        self._app = application
        self._awatch = awatch(
            self._path,
            stop_event=self.stopper,
            watch_filter=CloudollFilter(
                tuple(self._config["server"].get("ignore_dirs", []))
            ),
        )
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        raise NotImplementedError

    async def close(self, *args: Any) -> None:
        self.stopper.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def cleanup_ctx(self, application: web.Application) -> AsyncIterator[None]:
        try:
            await self.start(application)
            yield
        finally:
            await self.close()


@contextlib.contextmanager
def set_tty(tty_path: Optional[str]) -> Iterator[None]:
    original = sys.stdin
    tty = None
    if tty_path:
        try:
            tty = open(tty_path)
        except OSError:
            pass
    try:
        if tty is not None:
            sys.stdin = tty
        yield
    finally:
        sys.stdin = original
        if tty is not None:
            tty.close()


def mian_app(
    tty_path: Optional[str],
    config: dict[str, Any],
    entry: Optional[str],
    env: str,
    ready: Any = None,
    stop: Any = None,
) -> None:
    """Child entry point; keep the legacy name for import compatibility."""

    async def serve() -> None:
        runner = await create_main_app(config, entry, env)
        try:
            await start_main_app(
                runner,
                config["server"]["host"],
                config["server"]["port"],
                config["server"].get("path"),
            )
            if ready is not None:
                ready.send((True, ""))
            while stop is None or not stop.is_set():
                await asyncio.sleep(0.05)
        finally:
            await runner.cleanup()

    with set_tty(tty_path):
        try:
            asyncio.run(serve())
        except KeyboardInterrupt:
            pass
        except BaseException as exc:
            if ready is not None:
                with contextlib.suppress(OSError):
                    ready.send((False, f"{type(exc).__name__}: {exc}"))
            raise
        finally:
            if ready is not None:
                ready.close()


async def create_main_app(
    config: dict[str, Any], entry: Optional[str], env: str
) -> web.AppRunner:
    application: Application = app.current().create(
        env=env, config=config, entry_model=entry
    )
    assert application.app is not None
    # Bind once: probing 0.0.0.0 was racy and ignored the actual bind address.
    return web.AppRunner(application.app, shutdown_timeout=2)


async def start_main_app(
    runner: web.AppRunner, host: str, port: int, path: Optional[str] = None
) -> None:
    await runner.setup()
    site: web.BaseSite
    if path is not None:
        site = web.UnixSite(runner, path)
    else:
        site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    info("Development server ready on %s", path or f"http://{host}:{port}")


class AppTask(WatchTask):
    def __init__(
        self,
        watch_path: Union[str, Path],
        config: dict[str, Any],
        entry: Optional[str],
        env: str,
    ) -> None:
        super().__init__(watch_path)
        self._config = config
        self._entry = entry
        self._env = env
        self._reloads = 0
        self._process: Optional[Process] = None
        self._stop_event: Any = None
        self._close_task: Optional[asyncio.Task[None]] = None
        self.failure: Optional[BaseException] = None
        self._closing = False

    async def start(self, application: web.Application) -> None:
        # A spawned PID alone does not mean the HTTP application started.
        await self._start_dev_server()
        await super().start(application)
        assert self._task is not None
        self._task.add_done_callback(self._completed)

    def _completed(self, task: asyncio.Task[None]) -> None:
        if self._closing or task.cancelled():
            return
        self.failure = task.exception() or RuntimeError(
            "Development watcher exited unexpectedly"
        )
        # aiohttp catches GracefulExit and cleans up; CLI then reports failure.
        raise web.GracefulExit()

    async def _watch_changes(self) -> None:
        async for changes in self._awatch:
            if self.stopper.is_set():
                return
            if any(filename.endswith(".py") for _, filename in changes):
                self._reloads += 1
                await self._stop_dev_server()
                if not self.stopper.is_set():
                    await self._start_dev_server()

    async def _monitor(self) -> None:
        while not self.stopper.is_set():
            process = self._process
            if process is not None and not process.is_alive():
                raise RuntimeError(
                    f"Development server exited (code {process.exitcode})"
                )
            await asyncio.sleep(0.1)

    async def _run(self) -> None:
        tasks = [
            asyncio.create_task(self._watch_changes()),
            asyncio.create_task(self._monitor()),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
        finally:
            self.stopper.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _start_dev_server(self) -> None:
        try:
            tty_path = os.ttyname(sys.stdin.fileno())
        except (OSError, AttributeError, ValueError):
            tty_path = None
        receiver, sender = Pipe(duplex=False)
        self._stop_event = Event()
        process = Process(
            target=mian_app,
            args=(
                tty_path,
                self._config,
                self._entry,
                self._env,
                sender,
                self._stop_event,
            ),
        )
        try:
            try:
                process.start()
            except BaseException:
                process.close()
                raise
            self._process = process
            sender.close()
            deadline = asyncio.get_running_loop().time() + 30
            while True:
                if receiver.poll():
                    try:
                        success, message = receiver.recv()
                    except EOFError as exc:
                        raise RuntimeError(
                            "Development server closed its startup channel"
                        ) from exc
                    if not success:
                        raise RuntimeError(
                            f"Development server startup failed: {message}"
                        )
                    return
                if not process.is_alive():
                    raise RuntimeError(
                        f"Development server exited during startup (code {process.exitcode})"
                    )
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("Development server startup exceeded 30 seconds")
                await asyncio.sleep(0.05)
        finally:
            receiver.close()
            sender.close()

    async def _stop_dev_server(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        stop = self._stop_event

        def stop_process() -> None:
            if stop is not None:
                stop.set()
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
            if process.is_alive():
                raise RuntimeError("Could not stop development server process")
            process.close()

        # Cancellation must not abandon a live process or race a replacement.
        worker = asyncio.create_task(asyncio.to_thread(stop_process))
        cancelled = False
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancelled = True
        worker.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _close(self) -> None:
        try:
            await super().close()
        finally:
            await self._stop_dev_server()

    async def close(self, *args: Any) -> None:
        self._closing = True
        self.stopper.set()
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        cancelled = False
        while not self._close_task.done():
            try:
                await asyncio.shield(self._close_task)
            except asyncio.CancelledError:
                cancelled = True
        self._close_task.result()
        if cancelled:
            raise asyncio.CancelledError
