"""Production extension points participate in the public strict typing contract."""

from cloudoll.logging import configure_logging
from cloudoll.observability import Event, observation_scope, trace_context
from cloudoll.orm.engine import AsyncEngine
from cloudoll.web import Application, jwt


def observe(event: Event) -> None:
    duration: float = event.duration_seconds
    route: str = event.route
    invalid: int = event.route  # type: ignore[assignment]


def contract(db: AsyncEngine, token: str, key: str) -> None:
    app: Application = Application(observer=observe)
    with observation_scope(observe), trace_context("1" * 32, "2" * 16):
        counts: dict[str, int] = db.pool_stats()
        configure_logging(format="json", redact=lambda text: text)
        claims = jwt.decode(
            token, key, issuer="issuer", audience=["client"], require=("exp",)
        )
        if claims is not None:
            subject: object = claims.get("sub")
    Application(observer="invalid")  # type: ignore[arg-type]
