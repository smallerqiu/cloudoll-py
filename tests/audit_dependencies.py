"""Audit the exact installed versions, excluding only this local project.

    python tests/audit_dependencies.py

The generated requirements and JSON report are release-review artifacts.
"""

import argparse
import json
import subprocess
import sys
from importlib.metadata import distributions
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("dist/audit"))
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    requirements = set()
    for distribution in distributions():
        name = distribution.metadata["Name"]
        if name.lower().replace("_", "-") == "cloudoll":
            continue
        direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
        if direct_url.get("dir_info", {}).get("editable"):
            raise RuntimeError(f"Cannot audit editable dependency: {name}")
        requirements.add(f"{name}=={distribution.version}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    requirements_file = args.output_dir / "requirements.txt"
    requirements_file.write_text(
        "\n".join(sorted(requirements)) + "\n", encoding="utf-8"
    )
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "--strict",
        "--no-deps",
        "--disable-pip",
        "--progress-spinner",
        "off",
        "--requirement",
        str(requirements_file),
        "--format=json",
        "--output",
        str(args.output_dir / "report.json"),
    ]
    if args.cache_dir is not None:
        command.extend(["--cache-dir", str(args.cache_dir)])
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
