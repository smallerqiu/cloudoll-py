"""Offline documentation queries and non-destructive project setup."""

from importlib.resources import files
from pathlib import Path

import click

BEGIN = "<!-- cloudoll-ai:start -->"
END = "<!-- cloudoll-ai:end -->"


def document_topics() -> list[str]:
    return sorted(
        p.name[:-3]
        for p in files("cloudoll.ai").joinpath("docs").iterdir()
        if p.name.endswith(".md")
    )


def read_document(topic: str) -> str:
    if topic not in document_topics():
        raise click.ClickException("Unknown topic. Run `cloudoll ai list`.")
    return (
        files("cloudoll.ai")
        .joinpath("docs")
        .joinpath(topic + ".md")
        .read_text(encoding="utf-8")
    )


def initialize_project(directory: Path) -> None:
    """Preserve user instructions; refuse to replace a customized skill."""
    agents = directory / "AGENTS.md"
    skill = directory / ".agents" / "skills" / "cloudoll" / "SKILL.md"
    resource = files("cloudoll.ai")
    skill_text = (
        resource.joinpath("skills")
        .joinpath("cloudoll")
        .joinpath("SKILL.md")
        .read_text(encoding="utf-8")
    )
    instructions = resource.joinpath("AGENTS.md").read_text(encoding="utf-8")
    original = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if agents.is_symlink() or any(p.is_symlink() for p in (skill, *skill.parents)):
        raise click.ClickException(
            "Refusing to write AI instructions through a symbolic link."
        )
    if skill.exists() and skill.read_text(encoding="utf-8") != skill_text:
        raise click.ClickException(
            "Existing Cloudoll skill differs; review and merge it manually before initializing."
        )
    if original.count(BEGIN) != original.count(END) or original.count(BEGIN) > 1:
        raise click.ClickException(
            "Malformed Cloudoll block in AGENTS.md; repair it before initializing."
        )
    block = BEGIN + "\n" + instructions.rstrip() + "\n" + END
    if BEGIN in original:
        start, end = original.index(BEGIN), original.index(END)
        if end < start:
            raise click.ClickException("Malformed Cloudoll block in AGENTS.md.")
        updated = original[:start] + block + original[end + len(END) :]
    else:
        updated = original + ("\n\n" if original else "") + block + "\n"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(skill_text, encoding="utf-8")
    agents.write_text(updated, encoding="utf-8")


@click.group()
def ai() -> None:
    """Read bundled official docs and initialize project AI instructions (offline)."""


@ai.command("list")
def list_topics() -> None:
    """List available documentation topics."""
    click.echo("\n".join(document_topics()))


@ai.command("read")
@click.argument("topic")
def read_topic(topic: str) -> None:
    """Print an official documentation topic verbatim."""
    click.echo(read_document(topic))


@ai.command("search")
@click.argument("query")
def search(query: str) -> None:
    """Find matching lines, with topic and line number."""
    if not query.strip():
        raise click.ClickException("Search query must not be empty.")
    for topic in document_topics():
        for number, line in enumerate(read_document(topic).splitlines(), 1):
            if query.casefold() in line.casefold():
                click.echo(f"{topic}:{number}: {line}")


@ai.command("init")
@click.argument(
    "directory", type=click.Path(path_type=Path, file_okay=False), default="."
)
def init(directory: Path) -> None:
    """Install AGENTS.md guidance and a project-local Cloudoll skill."""
    initialize_project(directory)
    click.echo(f"Cloudoll AI instructions installed in {directory.absolute()}")
