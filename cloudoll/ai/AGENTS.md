## Cloudoll development

Before building or changing a Cloudoll application, read `.agents/skills/cloudoll/SKILL.md` completely and follow its documentation workflow. Use the project's Python environment, not a globally installed version.

Official documentation is bundled with the installed library: `python -m cloudoll.cli ai list`, `ai read <topic>`, and `ai search <query>`. These commands work offline without MCP. Read `structure`, `config`, `router`, and `validation` before designing an application; read `database` before database work. Consult the installed source when resolving a signature discrepancy; report the discrepancy rather than inventing an API.

Prefer the documented scaffold, auto-discovered controllers/middlewares, YAML configuration, framework-owned database lifecycle, typed request validation, and ORM for ordinary CRUD. Low-level alternatives require a task-specific reason. Never silently replace Cloudoll's architecture with patterns from another framework.
