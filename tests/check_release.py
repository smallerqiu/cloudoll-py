"""Verify built metadata matches source, and a release tag if supplied by CI."""

import os
import sys
import zipfile
from email.parser import Parser
from pathlib import Path


def check(wheel: Path, tag: str = "") -> None:
    # Read source version without importing an installed distribution by mistake.
    import ast

    source = Path(__file__).resolve().parents[1] / "cloudoll" / "__init__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    versions = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
    ]
    assert len(versions) == 1, "Expected one literal package version"
    with zipfile.ZipFile(wheel) as archive:
        names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        assert len(names) == 1, "Expected one distribution metadata file"
        metadata = Parser().parsestr(archive.read(names[0]).decode("utf-8"))
        assert metadata["Name"] == "cloudoll"
        assert metadata["Version"] == versions[0], "Wheel/source version mismatch"
        if tag:
            assert tag == "v" + versions[0], "Release tag/wheel version mismatch"
    print("Package metadata/source/tag consistency: OK")


if __name__ == "__main__":
    tag = (
        os.environ.get("GITHUB_REF_NAME", "")
        if os.environ.get("GITHUB_REF_TYPE") == "tag"
        else ""
    )
    check(Path(sys.argv[1]), tag)
