"""Bundle authoritative docs and generate LLM discovery files. No network needed."""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    docs_root = args.docs_root.resolve()
    sources = sorted((docs_root / "src/views").glob("*.md"))
    if not sources:
        parser.error("No documentation found in --docs-root/src/views")
    version_match = re.search(
        r'__version__ = "([^"]+)"', (ROOT / "cloudoll/__init__.py").read_text()
    )
    assert version_match
    version = version_match[1]
    outputs: dict[Path, str] = {}
    manifest: dict[str, object] = {"version": version, "documents": {}}
    records = {}
    links = [
        "# Cloudoll",
        "",
        f"> Official Python framework documentation snapshot for {version}.",
        "",
        "Use the installed version's `cloudoll ai list/read/search` commands for offline, version-matched documentation.",
        "",
        "## Documentation",
        "",
    ]
    full = ["# Cloudoll official documentation", "", f"Version: {version}", ""]
    for source in sources:
        content = source.read_text(encoding="utf-8")
        route_match = re.search(r"^path: (.+)$", content, re.M)
        route = route_match[1].strip() if route_match else "/" + source.stem
        url = "https://cloudoll.chuchur.com" + route
        records[source.stem] = {
            "source": "src/views/" + source.name,
            "url": url,
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
        }
        outputs[ROOT / "cloudoll/ai/docs" / source.name] = content
        links.append(f"- [{source.stem}]({url})")
        full.extend([f"## Source: {url}", "", content, ""])
    manifest["documents"] = records
    outputs[ROOT / "cloudoll/ai/manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    outputs[docs_root / "public/llms.txt"] = "\n".join(links) + "\n"
    outputs[docs_root / "public/llms-full.txt"] = "\n".join(full) + "\n"
    stale = set((ROOT / "cloudoll/ai/docs").glob("*.md")) - set(outputs)
    if stale:
        parser.error(
            "Remove obsolete bundled topics after review: "
            + ", ".join(map(str, sorted(stale)))
        )
    mismatches = []
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                mismatches.append(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    if mismatches:
        parser.exit(
            1, "AI documentation is out of date:\n" + "\n".join(mismatches) + "\n"
        )
    print(
        f"{'Checked' if args.check else 'Generated'} {len(sources)} documentation topics for Cloudoll {version}."
    )


if __name__ == "__main__":
    main()
