import json
import logging
from datetime import date
from unittest.mock import Mock

import click
import pytest

from cloudoll.clitool.process import ProcessManager
from cloudoll.logging import DailyFileHandler
from cloudoll.orm.model import Model, models


def test_composite_primary_key_is_rejected():
    with pytest.raises(ValueError, match="Composite primary"):

        class Unsafe(Model):
            tenant = models.IntegerField(primary_key=True)
            id = models.IntegerField(primary_key=True)


@pytest.mark.parametrize(
    "name", ["state", "params", "pool", "compiler", "dialect", "record", "model"]
)
def test_query_internal_names_do_not_corrupt_fields(name):
    Record = type(
        "Record",
        (Model,),
        {"id": models.IntegerField(primary_key=True), name: models.IntegerField()},
    )
    query = Record.use(None)
    sql, args = query.where(Record.id == 1).test()
    assert "WHERE" in sql and args == [1]
    record = Record(**{name: 8})
    assert record[name].value == 8
    assert query.clone().test() == (sql, args)


@pytest.mark.parametrize(
    "name", ["../outside", "/tmp/outside", "a/b", "a\\b", "..", "", "a" * 65]
)
def test_service_name_cannot_escape_runtime(name, tmp_path, monkeypatch):
    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: tmp_path)
    with pytest.raises(click.ClickException):
        ProcessManager.save_start_args(name, [])
    assert not list(tmp_path.iterdir())


def test_pid_reuse_never_signals_process(tmp_path, monkeypatch):
    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: tmp_path)
    command = ["cloudoll", "start", "-n", "api"]
    (tmp_path / "api.pid").write_text(
        json.dumps({"pid": 123, "created": 1, "cmdline": command})
    )
    process = Mock(
        cmdline=Mock(return_value=command),
        create_time=Mock(return_value=2),
        is_running=Mock(return_value=True),
        status=Mock(return_value="running"),
    )
    monkeypatch.setattr(
        "cloudoll.clitool.process.psutil.Process", Mock(return_value=process)
    )
    ProcessManager.safe_exit("api")
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_start_context_preserves_directory_and_symlink_target(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: runtime)
    monkeypatch.chdir(project)
    target = tmp_path / "untouched"
    target.write_text("original")
    try:
        (runtime / "api.args").symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    ProcessManager.save_start_args("api", ["start", "-n", "api"])
    assert target.read_text() == "original"
    monkeypatch.chdir(tmp_path)
    assert ProcessManager.load_start_context("api") == (
        ["start", "-n", "api"],
        str(project),
    )


def test_legacy_pid_is_not_automatically_trusted(tmp_path, monkeypatch):
    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: tmp_path)
    (tmp_path / "api.pid").write_text("123")
    with pytest.raises(click.ClickException, match="Legacy PID"):
        ProcessManager.get_running_pid("api")


def test_saved_identity_checks_command_as_well_as_creation_time(tmp_path, monkeypatch):
    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: tmp_path)
    process = Mock(
        cmdline=Mock(return_value=["cloudoll", "start", "-n", "api"]),
        create_time=Mock(return_value=12.5),
        is_running=Mock(return_value=True),
        status=Mock(return_value="running"),
    )
    monkeypatch.setattr(
        "cloudoll.clitool.process.psutil.Process", Mock(return_value=process)
    )
    ProcessManager.save_pid("api", 123)
    assert ProcessManager.get_running_pid("api") == 123
    process.cmdline.return_value = ["other-program", "-n", "api"]
    assert ProcessManager.get_running_pid("api") is None


def test_missing_restart_directory_does_not_stop_service(tmp_path, monkeypatch):
    from cloudoll.cli import restart

    monkeypatch.setattr(ProcessManager, "get_running_pid", lambda _: 123)
    monkeypatch.setattr(
        ProcessManager,
        "load_start_context",
        lambda _: (["start"], str(tmp_path / "missing")),
    )
    stop = Mock()
    monkeypatch.setattr(ProcessManager, "safe_exit", stop)
    with pytest.raises(click.ClickException, match="unavailable"):
        restart.callback("api", False)
    stop.assert_not_called()


def test_duplicate_start_preserves_arguments(monkeypatch):
    from cloudoll.clitool import cli_main

    monkeypatch.setattr(cli_main, "get_config", lambda _: {})
    monkeypatch.setattr(ProcessManager, "ensure_runtime_dir", lambda: None)
    monkeypatch.setattr(ProcessManager, "get_running_pid", lambda _: 123)
    save = Mock()
    monkeypatch.setattr(ProcessManager, "save_start_args", save)
    cli_main.run_app(mode="production", environment="local", name="api")
    save.assert_not_called()


def test_restart_restores_project_before_exec(tmp_path, monkeypatch):
    from cloudoll.cli import restart

    monkeypatch.setattr(ProcessManager, "get_running_pid", lambda _: 123)
    monkeypatch.setattr(
        ProcessManager,
        "load_start_context",
        lambda _: (["start", "-n", "api"], str(tmp_path)),
    )
    stop = Mock()
    monkeypatch.setattr(ProcessManager, "safe_exit", stop)
    monkeypatch.chdir(tmp_path.parent)

    def execute(executable, args):
        from pathlib import Path

        assert Path.cwd() == tmp_path
        assert args[1:3] == ["-m", "cloudoll.cli"]

    monkeypatch.setattr("cloudoll.cli.os.execvp", execute)
    restart.callback("api", False)
    stop.assert_called_once_with("api")


def test_log_filter_and_retention(tmp_path, monkeypatch):
    monkeypatch.setattr("cloudoll.logging._get_log_dir", lambda: tmp_path)
    handler = DailyFileHandler("error", logging.ERROR, filter_exact=True)
    sink = Mock()
    handler.handler.emit = sink
    for level in (logging.ERROR, logging.CRITICAL):
        handler.handle(logging.LogRecord("cloudoll", level, "", 0, "test", (), None))
    assert [call.args[0].levelno for call in sink.call_args_list] == [logging.ERROR]
    for name in (
        "2020-01-01-all.log",
        "2020-01-01-error.log.1",
        "2020-01-17-all.log",
        "unrelated.log",
    ):
        (tmp_path / name).touch()
    handler._prune_logs(date(2020, 1, 30))
    assert not (tmp_path / "2020-01-01-all.log").exists()
    assert not (tmp_path / "2020-01-01-error.log.1").exists()
    assert (tmp_path / "2020-01-17-all.log").exists()
    assert (tmp_path / "unrelated.log").exists()
    handler.close()
