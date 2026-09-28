"""Static type contract; checked by mypy, never executed as a database test."""

from collections.abc import AsyncIterator
from typing import Any, Optional, Union

from cloudoll.orm import Query, Relation, Subquery
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
    mapping_row: Optional[dict[str, Any]] = await query.one_dict()
    present: bool = await query.exists()
    locked: Query[User] = query.for_update(skip_locked=True).distinct(False)
    expression: Subquery = User.use(db).select(1).subquery()
    exists_expression: Subquery = User.use(db).exists_expr()
    combined: Query[User] = query.where_exists(User.use(db), negated=True)
    alias: Relation[User] = User.alias("u")
    aliased_query: Query[User] = alias.use(db)
    cte: Relation[User] = User.use(db).select().cte("users_cte")
    cte_query: Query[User] = cte.query()
    union: Query[User] = query.union_all(User.use(db))
    upserted: bool = await User.use(db).upsert({"id": 1}, update_fields=["id"])
    wrong_alias: Relation[Other] = User.alias("other")  # type: ignore[assignment]
    async with query.stream(batch_size=50) as rows:
        typed_rows: AsyncIterator[dict[str, Any]] = rows
        async for row in typed_rows:
            mapping: dict[str, Any] = row
    # Strict unused-ignore checking makes these assertions fail if inference degrades to Any.
    incompatible: Query[Other] = User.use(db)  # type: ignore[assignment]
    wrong_user: Optional[Other] = await query.one_model()  # type: ignore[assignment]
    wrong_rows: list[User] = await query.all()  # type: ignore[assignment]
