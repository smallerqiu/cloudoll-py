# Cloudoll library maintenance

This repository implements Cloudoll; it is not a generated application. Read `AI.md` before changing AI assets. Public API behavior must be verified against source and tests, not inferred from other frameworks. The application-development skill is `cloudoll/ai/skills/cloudoll/SKILL.md`; read it when creating application examples.

Official documentation is maintained in the sibling `cloudoll-py-docs` repository, under `src/views`. Bundled copies in `cloudoll/ai/docs` are generated: edit the original docs, then run the sync command in `AI.md`. Update docs and tests together when changing public behavior. Preserve Python 3.9 compatibility.
