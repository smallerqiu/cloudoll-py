import asyncio
import io
import multiprocessing
import os
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web

from cloudoll import __version__
from cloudoll.clitool import cli_main, watch
from cloudoll.web import Application, app
from cloudoll.web.context import active_application


@pytest.mark.parametrize(
    "failure", [None, OSError("body failure"), ValueError("body failure")]
)
def test_tty_restores_input_and_preserves_body_error(monkeypatch, failure):
    old = sys.stdin
    tty = io.StringIO("test")
    monkeypatch.setattr("builtins.open", lambda _: tty)
    try:
        with watch.set_tty("tty"):
            assert sys.stdin is tty
            if failure is not None:
                raise failure
    except Exception as exc:
        assert exc is failure
    assert sys.stdin is old
    assert tty.closed


def test_tty_open_failure_does_not_catch_body_error(monkeypatch):
    monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("no tty")))
    old = sys.stdin
    error = OSError("body")
    with pytest.raises(OSError) as caught:
        with watch.set_tty("tty"):
            assert sys.stdin is old
            raise error
    assert caught.value is error


def test_watch_filter_always_skips_logs_and_project_dirs():
    from watchfiles import Change

    def watched(*parts: str) -> str:
        # watchfiles reports a change with the platform separator and splits the
        # path on it, so the filter is only ever seen with such paths.
        return os.sep.join(parts)

    chosen = watch.CloudollFilter(("build", "dist"))
    for path in (
        watched("logs", "access.log"),
        watched("build", "x.py"),
        watched("dist", "app.js"),
        watched(".venv", "x.py"),
    ):
        assert not chosen(Change.modified, path), path
    assert chosen(Change.modified, watched("controllers", "home", "index.py"))
    # The project list must not replace watchfiles' own defaults.
    assert not chosen(Change.modified, watched("__pycache__", "model.pyc"))
    assert not chosen(Change.modified, watched(".git", "config"))
    default = watch.CloudollFilter()
    assert not default(Change.modified, watched("logs", "access.log"))
    assert default(Change.modified, watched("dist", "app.js"))


def test_development_server_uses_merged_host(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "get_config",
        lambda _: {"server": {"host": "127.0.0.1", "port": 9001}},
    )
    seen = []

    def fake_task(path, config, entry, env):
        seen.append(config)
        return SimpleNamespace(cleanup_ctx=Mock(), failure=None)

    monkeypatch.setattr(cli_main, "AppTask", fake_task)
    supervisor = Mock()
    monkeypatch.setattr(cli_main, "run_supervisor", supervisor)
    cli_main.run_app(mode="development", environment="local", entry=None)
    # The worker process owns the only socket, and it binds the merged config.
    assert seen[0]["server"] == {"host": "127.0.0.1", "port": 9001, "path": None}
    assert not list(supervisor.call_args.args[0].router.routes())


def test_cli_host_overrides_the_development_config(monkeypatch):
    monkeypatch.setattr(
        cli_main, "get_config", lambda _: {"server": {"host": "10.0.0.1", "port": 8000}}
    )
    seen = []
    monkeypatch.setattr(
        cli_main,
        "AppTask",
        lambda path, config, entry, env: (
            seen.append(config) or SimpleNamespace(cleanup_ctx=Mock(), failure=None)
        ),
    )
    monkeypatch.setattr(cli_main, "run_supervisor", Mock())
    cli_main.run_app(
        mode="development", environment="local", entry=None, host="0.0.0.0", port=9100
    )
    assert seen[0]["server"]["host"] == "0.0.0.0"
    assert seen[0]["server"]["port"] == 9100


def test_development_defaults_to_the_local_interface(monkeypatch):
    monkeypatch.setattr(cli_main, "get_config", lambda _: {})
    seen = []
    monkeypatch.setattr(
        cli_main,
        "AppTask",
        lambda path, config, entry, env: (
            seen.append(config) or SimpleNamespace(cleanup_ctx=Mock(), failure=None)
        ),
    )
    monkeypatch.setattr(cli_main, "run_supervisor", Mock())
    cli_main.run_app(mode="development", environment="local", entry=None)
    # An unspecified listen address must not expose the app to the network.
    assert seen[0]["server"]["host"] == "127.0.0.1"
    assert seen[0]["server"]["port"] == 9001


def test_library_run_defaults_to_the_local_interface(tmp_path, monkeypatch):
    application = Application(root=tmp_path)
    application.create(entry_model=None, config={})
    run = Mock()
    monkeypatch.setattr(application, "app", Mock())
    monkeypatch.setattr(cli_main.web, "run_app", run)
    application.run()
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 9001


def test_supervisor_runs_without_a_listening_socket(monkeypatch):
    def refuse(*args, **kw):
        raise AssertionError("the supervisor must not bind a port")

    monkeypatch.setattr(watch.web, "TCPSite", refuse)
    monkeypatch.setattr(watch.web, "UnixSite", refuse)
    monkeypatch.setattr(watch.web, "SockSite", refuse)
    stages = []

    async def lifecycle(application):
        stages.append("started")

        def failure() -> None:
            # This is how AppTask._completed ends supervision.
            raise web.GracefulExit()

        asyncio.get_running_loop().call_soon(failure)
        yield
        stages.append("stopped")

    supervisor_app = web.Application()
    supervisor_app.cleanup_ctx.append(lifecycle)
    watch.run_supervisor(supervisor_app)
    assert stages == ["started", "stopped"]


def task(tmp_path):
    return watch.AppTask(
        tmp_path, {"server": {"host": "127.0.0.1", "port": 0}}, None, "local"
    )


async def test_partial_start_failure_cleans_up_and_propagates(tmp_path, monkeypatch):
    supervisor = task(tmp_path)
    process = Mock()
    error = OSError("spawn failed")
    process.start.side_effect = error
    monkeypatch.setattr(watch, "Process", Mock(return_value=process))
    receiver, sender = Mock(), Mock()
    monkeypatch.setattr(watch, "Pipe", lambda **kw: (receiver, sender))
    monkeypatch.setattr(watch, "Event", Mock())
    context = supervisor.cleanup_ctx(web.Application())
    with pytest.raises(OSError) as caught:
        await context.__anext__()
    assert caught.value is error
    assert supervisor._process is None
    process.close.assert_called_once()
    receiver.close.assert_called_once()
    sender.close.assert_called_once()
    await supervisor.close()


async def test_startup_handshake_error_reaps_child(tmp_path, monkeypatch):
    supervisor = task(tmp_path)
    process = Mock()
    process.is_alive.return_value = False
    monkeypatch.setattr(watch, "Process", Mock(return_value=process))
    receiver, sender = Mock(), Mock()
    receiver.poll.return_value = True
    receiver.recv.return_value = (False, "port busy")
    monkeypatch.setattr(watch, "Pipe", lambda **kw: (receiver, sender))
    monkeypatch.setattr(watch, "Event", Mock())
    with pytest.raises(RuntimeError, match="port busy"):
        await supervisor.cleanup_ctx(web.Application()).__anext__()
    process.join.assert_called_once_with(5)
    process.close.assert_called_once()


async def test_stop_does_not_block_loop_and_survives_cancellation(tmp_path):
    supervisor = task(tmp_path)
    entered, release = threading.Event(), threading.Event()
    process = Mock()
    process.is_alive.return_value = False

    def join(timeout):
        entered.set()
        assert release.wait(2), "event loop was blocked by join"

    process.join.side_effect = join
    supervisor._process = process
    supervisor._stop_event = Mock()
    closing = asyncio.create_task(supervisor.close())
    try:
        while not entered.is_set():
            await asyncio.sleep(0.001)
        closing.cancel()
        await asyncio.sleep(0)
        assert not closing.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await closing
    process.close.assert_called_once()
    await supervisor.close()
    process.join.assert_called_once()


async def test_stop_escalates_only_after_grace_period(tmp_path):
    supervisor = task(tmp_path)
    process = Mock()
    process.is_alive.side_effect = [True, True, False]
    supervisor._process = process
    supervisor._stop_event = Mock()
    await supervisor.close()
    assert [call.args for call in process.join.call_args_list] == [(5,), (1,), (1,)]
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    process.close.assert_called_once()


async def test_reload_stops_old_before_starting_new(tmp_path):
    supervisor = task(tmp_path)
    calls = []

    async def changes():
        yield {(1, "change.py")}

    async def stop():
        calls.append("stop")

    async def start():
        calls.append("start")

    supervisor._awatch = changes()
    supervisor._stop_dev_server = stop
    supervisor._start_dev_server = start
    await supervisor._watch_changes()
    assert calls == ["stop", "start"]


async def test_child_death_is_reported(tmp_path):
    supervisor = task(tmp_path)
    supervisor._process = Mock(is_alive=Mock(return_value=False), exitcode=3)
    with pytest.raises(RuntimeError, match="code 3"):
        await supervisor._monitor()


async def test_background_failure_requests_cli_shutdown(tmp_path):
    supervisor = task(tmp_path)
    failed = asyncio.create_task(AsyncMock(side_effect=RuntimeError("watch failed"))())
    await asyncio.gather(failed, return_exceptions=True)
    with pytest.raises(web.GracefulExit):
        supervisor._completed(failed)
    assert str(supervisor.failure) == "watch failed"


@pytest.mark.parametrize("start_method", multiprocessing.get_all_start_methods())
@pytest.mark.parametrize("inherited", ["context", "default"])
async def test_real_child_readiness_reload_and_cleanup(
    tmp_path, monkeypatch, unused_tcp_port, start_method, inherited, capfd
):
    monkeypatch.setenv("CLOUDOLL_LOG_DIR", str(tmp_path / "logs"))
    context = multiprocessing.get_context(start_method)
    for name in ("Process", "Pipe", "Event"):
        monkeypatch.setattr(watch, name, getattr(context, name))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "entry.py").write_text(
        "from pathlib import Path\n"
        "async def on_startup(app):\n"
        "    with Path('started').open('a') as f: f.write('1')\n"
        "async def on_cleanup(app):\n"
        "    with Path('cleaned').open('a') as f: f.write('1')\n"
    )
    supervisor = watch.AppTask(
        tmp_path,
        {"server": {"host": "127.0.0.1", "port": unused_tcp_port}},
        "entry",
        "local",
    )
    # fork inherits context variables and cached applications from the parent.
    # The child must load its own project, not this unrelated parent's root.
    stale = Application(root=tmp_path / "parent-project")
    previous_default = object.__getattribute__(app, "_default")
    object.__setattr__(app, "_default", stale)
    token = active_application.set(stale if inherited == "context" else None)
    # The explicit project root must win even if the parent changes directory.
    monkeypatch.chdir(tmp_path.parent)
    try:
        await supervisor._start_dev_server()
        assert (tmp_path / "started").read_text() == "1"
        assert supervisor._process.is_alive()

        async def changes():
            yield {(1, "change.py")}

        supervisor._awatch = changes()
        await supervisor._watch_changes()
        assert (tmp_path / "started").read_text() == "11"
        assert (tmp_path / "cleaned").read_text() == "1"
    finally:
        active_application.reset(token)
        object.__setattr__(app, "_default", previous_default)
        await supervisor.close()
    assert (tmp_path / "cleaned").read_text() == "11"
    assert supervisor._process is None
    # The persistent forkserver retains the first test's stderr and environment.
    # Check log destinations in fresh spawn/fork children; all methods still
    # exercise the real readiness handshake, reload, and shutdown above.
    if start_method != "forkserver":
        output = capfd.readouterr().err
        assert output.count("development server ready on") == 2
        assert f"http://127.0.0.1:{unused_tcp_port}" in output
        log_files = list((tmp_path / "logs").glob("*-all.log"))
        assert log_files and "development server ready on" in log_files[0].read_text()


async def test_real_bind_failure_is_not_success(tmp_path, monkeypatch):
    import socket

    monkeypatch.setenv("CLOUDOLL_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.chdir(tmp_path)
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        supervisor = watch.AppTask(
            tmp_path,
            {"server": {"host": "127.0.0.1", "port": occupied.getsockname()[1]}},
            None,
            "local",
        )
        with pytest.raises(RuntimeError, match="startup failed"):
            await supervisor.cleanup_ctx(web.Application()).__anext__()
        assert supervisor._process is None


async def test_real_child_crash_exits_supervisor_with_failure(
    tmp_path, unused_tcp_port, monkeypatch
):
    monkeypatch.setenv("CLOUDOLL_LOG_DIR", str(tmp_path / "logs"))
    (tmp_path / "entry.py").write_text(
        "import asyncio, os\n"
        "async def on_startup(app):\n"
        "    asyncio.get_running_loop().call_later(0.5, os._exit, 3)\n"
    )
    script = (
        "from cloudoll.clitool import cli_main\n"
        f"cli_main.get_config = lambda _: {{'server': {{'host': '127.0.0.1', 'port': {unused_tcp_port}}}}}\n"
        "cli_main.run_app(mode='development', environment='local', entry='entry', name='test')\n"
    )
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "Development server supervision failed" in result.stderr
    assert "Development server exited (code 3)" in result.stderr


async def test_development_start_survives_a_busy_neighbouring_port(
    tmp_path, monkeypatch
):
    import socket

    monkeypatch.setenv("CLOUDOLL_LOG_DIR", str(tmp_path / "logs"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        business_port = probe.getsockname()[1]
    neighbour = socket.socket()
    try:
        # The supervisor used to bind business port + 1 for itself, so any service
        # already there stopped `cloudoll start` before the app could be reached.
        neighbour.bind(("127.0.0.1", business_port + 1))
    except OSError:
        pytest.skip(f"port {business_port + 1} belongs to another service")
    neighbour.listen()
    script = (
        "from cloudoll.clitool import cli_main\n"
        f"cli_main.get_config = lambda _: {{'server': {{'host': '127.0.0.1', 'port': {business_port}}}}}\n"
        "cli_main.run_app(mode='development', environment='local', entry=None, name='test')\n"
    )
    # Capture to a file, not a pipe: the supervisor starts a server child that
    # inherits the write end, and Windows stops only the supervisor, so a pipe
    # would never reach EOF and reading it would hang the suite.
    error_log = tmp_path / "supervisor.err"
    sink = error_log.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        stderr=sink,
        text=True,
    )
    child = None

    def stop_supervisor() -> int:
        if os.name == "nt":
            # Windows has no shutdown signal for the supervisor's own cleanup
            # path, and killing it alone leaves the server child running with
            # the port held.
            import psutil

            try:
                spawned = psutil.Process(process.pid).children(recursive=True)
            except psutil.Error:
                spawned = []
            for grandchild in spawned:
                try:
                    grandchild.kill()
                except psutil.Error:
                    pass
        process.terminate()
        return process.wait(15)

    try:

        async def wait_until_ready() -> None:
            deadline = asyncio.get_running_loop().time() + 20
            while True:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection("127.0.0.1", business_port), 1
                    )
                except OSError:
                    if process.poll() is not None:
                        raise AssertionError(
                            f"supervisor exited early: {error_log.read_text()}"
                        )
                else:
                    writer.close()
                    return
                if asyncio.get_running_loop().time() >= deadline:
                    raise AssertionError("development server never became ready")
                await asyncio.sleep(0.1)

        await asyncio.wait_for(wait_until_ready(), 25)
        await asyncio.sleep(0.5)
        assert process.poll() is None
        exit_code = await asyncio.to_thread(stop_supervisor)
        if os.name == "posix":
            # SIGTERM reaches the supervisor's own shutdown path, so stopping
            # cleanly is part of the contract there. Windows terminates the
            # process outright and reports the loader's status, not an exit code
            # the application chose.
            assert exit_code == 0
        child = error_log.read_text()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(5)
        neighbour.close()
        sink.close()
    assert "Address already in use" not in child
    assert "Traceback" not in child


@pytest.mark.parametrize("fail_startup", [False, True])
def test_application_run_announces_ready_only_after_startup(
    tmp_path, fail_startup, unused_tcp_port
):
    script = f"""
import asyncio
from aiohttp import web
from cloudoll.logging import configure_logging
from cloudoll.web import Application
configure_logging()
application = Application(root={str(tmp_path)!r}).create(config={{}}, entry_model=None)
def stop():
    raise web.GracefulExit()
async def startup(app):
    if {fail_startup!r}:
        raise RuntimeError("startup failed")
    asyncio.get_running_loop().call_later(0.2, stop)
application.app.on_startup.append(startup)
application.run(host="127.0.0.1", port={unused_tcp_port})
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if fail_startup:
        assert result.returncode != 0
        assert f"Cloudoll {__version__} ready\n" not in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert f"Cloudoll {__version__} ready\n" in result.stderr
        assert f"http://127.0.0.1:{unused_tcp_port}" in result.stderr
