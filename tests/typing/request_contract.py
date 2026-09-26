"""Request source aliases preserve the actual model type for editors and mypy."""

from pydantic import BaseModel

from cloudoll.web import Body, Form, Path, Query


class Parameters(BaseModel):
    page: int = 1


def request_contract(
    body: Body[Parameters],
    query: Query[Parameters],
    form: Form[Parameters],
    path: Path[Parameters],
) -> None:
    for model in (body, query, form, path):
        value: int = model.page
        invalid: str = model.page  # type: ignore[assignment]
        model.missing  # type: ignore[attr-defined]
