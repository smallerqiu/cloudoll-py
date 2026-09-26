"""Static type contract; checked by mypy, never executed as a database test."""

from collections.abc import AsyncIterator
from typing import Any, Optional, Union

from cloudoll.orm import Query
from cloudoll.orm.model import Model
from cloudoll.orm.protocols import DatabaseEngine


class User(Model):
    pass


class Other(Model):
    pass


async def query_contract(db: DatabaseEngine) -> None:
    implicit: Query[User] = User.query()
    wrong_implicit: Query[Other] = User.query()  # type: ignore[assignment]
    query: Query[User] = User.use(db).where("id > 0").order_by("id").limit(20).clone()
    user: Optional[User] = await query.one_model()
    legacy: Optional[Union[User, dict[str, Any]]] = await query.one()
    mappings: list[dict[str, Any]] = await query.all()
    async with query.stream(batch_size=50) as rows:
        typed_rows: AsyncIterator[dict[str, Any]] = rows
        async for row in typed_rows:
            mapping: dict[str, Any] = row
    # Strict unused-ignore checking makes these assertions fail if inference degrades to Any.
    incompatible: Query[Other] = User.use(db)  # type: ignore[assignment]
    wrong_user: Optional[Other] = await query.one_model()  # type: ignore[assignment]
    wrong_rows: list[User] = await query.all()  # type: ignore[assignment]
