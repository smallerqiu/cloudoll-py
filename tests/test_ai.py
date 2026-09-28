import hashlib
import json
from importlib.resources import files

import click
import pytest
from click.testing import CliRunner

from cloudoll import __version__
from cloudoll.ai.commands import ai, document_topics, initialize_project, read_document


def test_document_integrity():
    manifest = json.loads(
        files("cloudoll.ai").joinpath("manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == __version__
    assert set(manifest["documents"]) == set(document_topics())
    for topic, record in manifest["documents"].items():
        assert (
            hashlib.sha256(read_document(topic).encode()).hexdigest()
            == record["sha256"]
        )
        assert record["source"] == f"src/views/{topic}.md"
        assert record["url"].startswith("https://cloudoll.chuchur.com/")


def test_query_commands():
    runner = CliRunner()
    assert "database" in runner.invoke(ai, ["list"]).output
    result = runner.invoke(ai, ["read", "structure"])
    assert result.exit_code == 0
    assert result.output.rstrip() == read_document("structure").rstrip()
    assert "validation:" in runner.invoke(ai, ["search", "Body"]).output
    assert runner.invoke(ai, ["search", " "]).exit_code != 0
    assert runner.invoke(ai, ["read", "../../pyproject"]).exit_code != 0


def test_init_preserves_user_instructions_and_is_idempotent(tmp_path):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# My project\nUse our test command.\n", encoding="utf-8")
    initialize_project(tmp_path)
    first = agents.read_bytes()
    assert first.startswith(b"# My project\nUse our test command.\n")
    initialize_project(tmp_path)
    assert agents.read_bytes() == first
    skill = tmp_path / ".agents/skills/cloudoll/SKILL.md"
    skill.write_text("My custom skill", encoding="utf-8")
    with pytest.raises(click.ClickException, match="differs"):
        initialize_project(tmp_path)
    assert agents.read_bytes() == first
    assert skill.read_text() == "My custom skill"


@pytest.mark.parametrize(
    "content",
    [
        "<!-- cloudoll-ai:start -->",
        "<!-- cloudoll-ai:end -->\n<!-- cloudoll-ai:start -->",
    ],
)
def test_init_rejects_malformed_blocks(tmp_path, content):
    (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
    with pytest.raises(click.ClickException, match="Malformed"):
        initialize_project(tmp_path)
    assert (tmp_path / "AGENTS.md").read_text() == content
    assert not (tmp_path / ".agents").exists()


def test_init_rejects_symlink(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    try:
        (tmp_path / ".agents").symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable")
        raise
    with pytest.raises(click.ClickException, match="symbolic"):
        initialize_project(tmp_path)
    assert not list(target.iterdir())


def test_init_command_creates_directory(tmp_path):
    directory = tmp_path / "project"
    result = CliRunner().invoke(ai, ["init", str(directory)])
    assert result.exit_code == 0, result.output
    assert (directory / "AGENTS.md").is_file()
