"""`cloudoll create` is the first command an application author runs, so a failed
creation has to look like a failure: nothing half-written left behind, and a
non-zero exit code for the script that called it."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cloudoll.cli import cli
from cloudoll.clitool.cli_main import create_project


def _artifacts(root: Path) -> list[str]:
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo")
    )


@pytest.fixture
def fake_template(tmp_path, monkeypatch):
    """A template directory holding the bytecode a real import leaves behind."""
    template = tmp_path / "template"
    (template / "controllers").mkdir(parents=True)
    (template / "__pycache__").mkdir()
    (template / "config").mkdir()
    (template / "__pycache__" / "__init__.cpython-313.pyc").write_bytes(b"fake")
    (template / "controllers" / "__pycache__").mkdir()
    (template / "controllers" / "__pycache__" / "index.cpython-313.pyc").write_bytes(
        b"fake"
    )
    (template / "config" / "conf.local.yaml").write_text("app: {}\n", encoding="utf-8")
    (template / "controllers" / "index.py").write_text("index = 1\n", encoding="utf-8")
    (template / "__init__.py").write_text("# package\n", encoding="utf-8")
    monkeypatch.setattr("cloudoll.clitool.cli_main.files", lambda package: template)
    return template


def test_a_created_project_carries_no_bytecode(fake_template, tmp_path):
    project = tmp_path / "shop"
    create_project(str(project))
    assert (project / "__init__.py").is_file()
    assert (project / "controllers" / "index.py").is_file()
    assert (project / "config" / "conf.local.yaml").is_file()
    assert _artifacts(project) == []


def test_the_bundled_template_creates_a_project_without_artifacts(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["create", "shop"])
    assert result.exit_code == 0, result.output
    project = tmp_path / "shop"
    assert (project / "config" / "conf.local.yaml").is_file()
    assert (project / ".gitignore").is_file()
    assert _artifacts(project) == []


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "nested/..",
        "/",
        "my shop",
        "shop;rm -rf",
        "shop$(whoami)",
        "shop\\name",
    ],
)
def test_names_that_do_not_survive_a_shell_are_refused(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="letters, digits"):
        create_project(name)
    assert list(tmp_path.iterdir()) == []


def test_a_project_in_another_directory_is_still_allowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    create_project("../work/shop")
    assert (tmp_path.parent / "work" / "shop").is_dir()


def test_the_start_hint_offers_a_service_name_the_shell_accepts(
    fake_template, tmp_path, monkeypatch
):
    # The printed command names the project directory and the service, so a
    # nested path must not turn into `cloudoll start -n work/shop`.
    messages = []
    monkeypatch.setattr(
        "cloudoll.clitool.cli_main.info", lambda *args, **kw: messages.append(args)
    )
    project = tmp_path / "work" / "shop"
    create_project(str(project))
    hints = [args for args in messages if "cloudoll start" in str(args[0])]
    assert len(hints) == 1
    rendered = hints[0][0] % tuple(hints[0][1:])
    assert f"cd {project} && cloudoll start -n shop" in rendered


def test_an_existing_target_fails_instead_of_returning_quietly(tmp_path):
    (tmp_path / "shop").mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        create_project(str(tmp_path / "shop"))
    assert list((tmp_path / "shop").iterdir()) == []


def test_a_failed_creation_leaves_no_half_written_project(fake_template, monkeypatch):
    def broken(directory: Path) -> None:
        raise RuntimeError("AI assets failed")

    monkeypatch.setattr("cloudoll.ai.commands.initialize_project", broken)
    target = fake_template.parent / "shop"
    with pytest.raises(RuntimeError, match="AI assets failed"):
        create_project(str(target))
    assert not target.exists()


async def test_a_created_project_resolves_its_session_key(tmp_path, monkeypatch):
    # The secret only works if the config actually reads it: `get_config` runs
    # EnvYAML against the project's `.env`, and the session layer must find a
    # configured key instead of falling back to a per-process random one.
    monkeypatch.delenv("CLOUDOLL_SESSION_SECRET", raising=False)
    monkeypatch.delenv("CLOUDOLL_JWT_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["create", "shop"])
    assert result.exit_code == 0, result.output
    project = tmp_path / "shop"
    monkeypatch.chdir(project)

    from aiohttp import web

    from cloudoll.web import sessions
    from cloudoll.web.core import Application
    from cloudoll.web.settings import get_config

    config = get_config("local")
    in_dotenv = dict(
        line.split("=", 1)
        for line in (project / ".env").read_text().splitlines()
        if line.strip()
    )
    assert (
        config["session"]["secret_key"] == in_dotenv["CLOUDOLL_SESSION_SECRET"].strip()
    )
    assert config["jwt"]["key"] == in_dotenv["CLOUDOLL_JWT_SECRET"].strip()

    warnings = []
    monkeypatch.setattr(
        sessions, "warning", lambda message, *args: warnings.append(message)
    )
    application = Application()
    application.config = config
    with patch.object(sessions, "session_middleware"):
        await application._init_session(web.Application())
    assert warnings == []


def test_create_reports_a_bad_name_with_a_non_zero_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["create", "my shop"])
    assert result.exit_code == 2
    assert not (tmp_path / "my shop").exists()


def test_create_reports_a_taken_name_with_a_non_zero_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(cli, ["create", "shop"]).exit_code == 0
    result = CliRunner().invoke(cli, ["create", "shop"])
    assert result.exit_code == 2
    assert "cloudoll --help" in result.output
    assert (tmp_path / "shop" / "__init__.py").is_file()
