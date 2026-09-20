"""HTTP/client public contracts; these functions are not run by pytest."""

from aiohttp import ClientResponse, web

from cloudoll.web import Application, render_json
from cloudoll.web.requests import Session


async def contract(client: Session, application: Application) -> None:
    response: ClientResponse = await client.get("https://example.invalid")
    body: web.Response = render_json({"ok": True})
    wrong: int = await client.get("https://example.invalid")  # type: ignore[assignment]
    bad_response: str = render_json({})  # type: ignore[assignment]
    bad_app: str = application.create(entry_model=None)  # type: ignore[assignment]
