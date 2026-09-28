# AI-assisted Cloudoll development

For application developers, `cloudoll create PROJECT` installs an `AGENTS.md` entry and `.agents/skills/cloudoll/SKILL.md`. Existing projects can run `python -m cloudoll.cli ai init .`. Existing user instructions are preserved; a different/customized skill is never silently replaced.

No MCP server is required:

```sh
python -m cloudoll.cli ai list
python -m cloudoll.cli ai read structure
python -m cloudoll.cli ai read database
python -m cloudoll.cli ai search Body
```

Use the project's Python environment. Ask your coding agent to read the project `AGENTS.md` and Cloudoll skill before coding. Tools that do not discover these files automatically can be given the paths explicitly. These instructions improve discoverability; they cannot guarantee that every model obeys them.

## Maintaining the assets

`cloudoll/ai/docs` contains verbatim snapshots of the official site's Markdown, not hand-maintained API summaries. `manifest.json` records the library version, source path, public URL, and SHA-256 for every topic. Relative site links in these snapshots refer to https://cloudoll.chuchur.com.

From the library root, with the documentation repository available:

```sh
python scripts/sync_ai_docs.py --docs-root ../cloudoll-py-docs
python scripts/sync_ai_docs.py --docs-root ../cloudoll-py-docs --check
python -m pytest tests/test_ai.py
python -m build
python tests/check_wheel.py dist/cloudoll-VERSION-py3-none-any.whl
```

The sync also generates the site's `public/llms.txt` and `public/llms-full.txt`. Commit both repositories' changes. These files are discovery aids, not a replacement for version-matched local docs. When upgrading Cloudoll in an existing application, review its installed skill against the packaged skill and merge intentional changes; initialization refuses a differing skill to avoid overwriting custom instructions.

Before release, run the cross-repository `--check` command. Tests validate the packaged snapshot integrity and version; they cannot detect uncommitted changes in an unavailable documentation repository.
