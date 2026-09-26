from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar, Optional, TypeVar, Union, cast
from contextlib import AbstractAsyncContextManager

from cloudoll.logging import warning
from cloudoll.orm.field import Field
from cloudoll.orm.values import UNSET

if TYPE_CHECKING:
    from cloudoll.orm.protocols import DatabaseEngine
    from cloudoll.orm.query import Query
M = TypeVar("M", bound="Model")

_QUERY_METHODS = frozenset(
    {
        "select",
        "where",
        "having",
        "join",
        "order_by",
        "group_by",
        "limit",
        "offset",
        "test",
        "one",
        "one_model",
        "all",
        "count",
        "stream",
        "insert",
        "insert_batch",
        "update",
        "delete",
    }
)

__all__ = ("models", "Model")


class ModelMetaclass(type):
    # def __init__(self, **kw):
    #     pass
    # def __call__(cls, *args, **kwargs):
    #     instance = super().__call__(*args, **kwargs)
    #     # 在元类中处理拷贝逻辑
    #     return copy.copy(instance)

    def __new__(
        mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]
    ) -> ModelMetaclass:
        if name == "Model":
            return type.__new__(mcs, name, bases, attrs)
        table_name = attrs.get("__table__", None) or name
        primary_key = None
        fields = []
        inherited = {}
        for base in reversed(bases):
            for key in getattr(base, "__fields__", []):
                inherited[key] = copy.copy(getattr(base, key))
        attrs = {**inherited, **attrs}
        for k, v in attrs.items():
            if isinstance(v, Field):
                v.name = k
                v.full_name = f"`{table_name}`.{k}"
                if v.primary_key:
                    if primary_key:
                        raise ValueError(
                            f"Composite primary keys are not supported: {table_name}"
                        )
                    primary_key = k
                fields.append(k)

        if not primary_key:
            warning(f"{table_name} Missing primary key")
        defaults = {
            "__table__": table_name,
            "__primary_key__": primary_key,
            "__fields__": fields,
        }
        attrs.update(defaults)
        model = type.__new__(mcs, name, bases, attrs)
        return model

    def __repr__(self) -> str:
        return "<Model: %s>" % self.__name__

    def __getattr__(cls, name: str) -> Any:
        # Class-level operations get a fresh builder. Record-level operations
        # continue through Model.__getattr__ and retain their bound engine.
        if name in _QUERY_METHODS:

            def operation(*args: Any, **kwargs: Any) -> Any:
                return getattr(cls.query(), name)(*args, **kwargs)

            return operation
        raise AttributeError(name)


class Model(metaclass=ModelMetaclass):
    __table__: str
    __datasource__: ClassVar[Optional[str]] = None
    __primary_key__: Optional[str]
    __fields__: list[str]
    _original: dict[str, Any]

    def __init__(self, **kw: Any) -> None:
        object.__setattr__(self, "_original", {})
        for k in self.__fields__:
            f = copy.copy(getattr(type(self), k))
            f.value = UNSET
            f._record_field = True
            object.__setattr__(self, k, f)
        for k, v in kw.items():
            self[k] = v

        # super().__init__(self, **kw)

    def __str__(self) -> str:
        return "<Model: %s>" % self.__class__.__name__

    def __repr__(self) -> str:
        return "<Model: %s>" % self.__class__.__name__

    def to_dict(self, *, exclude_unset: bool = False) -> dict[str, Any]:
        _dict: dict[str, Any] = {}
        for key in self.__fields__:
            f = getattr(self, key)
            if f.value is UNSET:
                if not exclude_unset:
                    _dict[key] = None
            else:
                _dict[key] = f.value
        return _dict

    @property
    def dirty_fields(self) -> frozenset[str]:
        return frozenset(
            key
            for key in self.__fields__
            if self[key].value is not UNSET
            and (key not in self._original or self[key].value != self._original[key])
        )

    def _mark_clean(self: M, values: Optional[dict[str, Any]] = None) -> M:
        values = self.to_dict(exclude_unset=True) if values is None else values
        self._original.update(copy.deepcopy(values))
        return self

    def _copy_record(self: M) -> M:
        result = type(self)(**copy.deepcopy(self.to_dict(exclude_unset=True)))
        result._original = copy.deepcopy(self._original)
        return result

    # class to fun for cls(**)
    def __call__(self: M, **kw: Any) -> M:
        self.__init__(**kw)  # type: ignore[misc]  # Legacy reset intentionally dispatches to subclass initialization.

        return self

    def __getitem__(self, name: str) -> Any:
        return getattr(self, name)

    # # .['x']
    def __setitem__(self, name: str, value: Any) -> None:
        setattr(self, name, value)

    def __setattr__(self, name: str, value: Any) -> None:
        if hasattr(self, name):
            f = getattr(self, name)
            if isinstance(f, Field):
                s = copy.copy(f)
                s.value = value
                super().__setattr__(name, s)
            else:
                super().__setattr__(name, value)
        else:
            super().__setattr__(name, value)

    # for get
    def get(self, k: str, d: Any = None) -> Any:
        f = getattr(self, k, None)
        if isinstance(f, Field):
            return d if f.value is None or f.value is UNSET else f.value
        return d if f is None else f

    def _get_primary(self) -> tuple[Optional[str], Any]:
        pk = self.__primary_key__
        if pk is None:
            return None, None
        if pk in self._original:
            return pk, self._original[pk]
        pkf = getattr(self, pk)
        return pk, None if pkf.value is UNSET else pkf.value

    @classmethod
    def use(cls: type[M], pool: Optional[DatabaseEngine]) -> Query[M]:
        from cloudoll.orm.query import Query

        return Query(cls, pool)

    @classmethod
    def query(cls: type[M]) -> Query[M]:
        """Create an independent query using this model's named datasource."""
        from cloudoll.orm.datasources import resolve_datasource

        return cls.use(resolve_datasource(cls.__datasource__))

    @classmethod
    def transaction(cls) -> AbstractAsyncContextManager[Any]:
        """Use the datasource's existing transaction/savepoint implementation."""
        from cloudoll.orm.datasources import resolve_datasource

        engine = resolve_datasource(cls.__datasource__)
        transaction = getattr(engine, "transaction", None)
        if not callable(transaction):
            raise TypeError("This datasource does not support transactions")
        return cast(AbstractAsyncContextManager[Any], transaction())

    def bind(self: M, pool: DatabaseEngine) -> M:
        """Bind this record for subsequent update/delete/insert operations."""
        self._bound_pool = pool
        return self

    def __getattr__(self, name: str) -> Any:
        # Compatibility facade: query operations live in Query, not in records.
        if name in _QUERY_METHODS:
            from cloudoll.orm.query import Query

            pool = self.__dict__.get("_bound_pool")
            return getattr(Query(type(self), pool, record=self), name)
        raise AttributeError(name)


class Models(object):
    class CharField(Field[str]):
        def __init__(
            self,
            name: Optional[str] = None,
            primary_key: bool = False,
            default: Optional[Any] = None,
            charset: Optional[str] = None,
            max_length: Optional[int] = None,
            not_null: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "char",
                default,
                primary_key,
                charset=charset,
                max_length=max_length,
                not_null=not_null,
                comment=comment,
            )

    class VarCharField(Field[str]):
        def __init__(
            self,
            name: Optional[str] = None,
            primary_key: bool = False,
            default: Optional[Any] = None,
            charset: Optional[str] = None,
            max_length: Optional[int] = None,
            not_null: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "varchar",
                default,
                primary_key,
                charset=charset,
                max_length=max_length,
                not_null=not_null,
                comment=comment,
            )

    class BooleanField(Field[bool]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = False,
            not_null: bool = False,
            comment: Optional[str] = None,
            unsigned: bool = False,
        ) -> None:
            super().__init__(
                name,
                "boolean",
                default,
                not_null=not_null,
                unsigned=unsigned,
                comment=comment,
            )

    class IntegerField(Field[int]):
        def __init__(
            self,
            name: Optional[str] = None,
            primary_key: bool = False,
            default: Optional[Any] = None,
            auto_increment: bool = False,
            not_null: bool = False,
            unsigned: bool = False,
            comment: Optional[str] = None,
            max_length: Optional[int] = None,
        ) -> None:
            super().__init__(
                name,
                "int",
                default,
                primary_key,
                auto_increment=auto_increment,
                not_null=not_null,
                unsigned=unsigned,
                comment=comment,
                max_length=max_length,
            )

    class BigIntegerField(Field[int]):
        def __init__(
            self,
            name: Optional[str] = None,
            primary_key: bool = False,
            default: Optional[Any] = None,
            auto_increment: bool = False,
            not_null: bool = False,
            unsigned: bool = False,
            comment: Optional[str] = None,
            max_length: Optional[int] = None,
        ) -> None:
            super().__init__(
                name,
                "bigint",
                default,
                primary_key,
                auto_increment=auto_increment,
                NOT_NULL=not_null,
                unsigned=unsigned,
                comment=comment,
                max_length=max_length,
            )

    class DoubleField(Field[float]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            not_null: bool = False,
            max_length: Optional[int] = None,
            unsigned: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "double",
                default,
                NOT_NULL=not_null,
                max_length=max_length,
                unsigned=unsigned,
                comment=comment,
            )

    class FloatField(Field[float]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            not_null: bool = False,
            max_length: Optional[int] = None,
            scale_length: Optional[int] = None,
            unsigned: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "float",
                default,
                NOT_NULL=not_null,
                max_length=max_length,
                scale_length=scale_length,
                unsigned=unsigned,
                comment=comment,
            )

    class NumericField(Field[Decimal]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = 0.0,
            not_null: bool = False,
            max_length: Optional[int] = None,
            scale_length: Optional[int] = None,
            unsigned: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "numeric",
                default,
                NOT_NULL=not_null,
                unsigned=unsigned,
                max_length=max_length,
                scale_length=scale_length,
                comment=comment,
            )

    class DecimalField(Field[Decimal]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = 0.0,
            not_null: bool = False,
            max_length: Optional[int] = None,
            scale_length: Optional[int] = None,
            unsigned: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "decimal",
                default,
                NOT_NULL=not_null,
                unsigned=unsigned,
                max_length=max_length,
                scale_length=scale_length,
                comment=comment,
            )

    class TextField(Field[str]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            charset: Optional[str] = None,
            max_length: Optional[int] = None,
            not_null: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "text",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class LongTextField(Field[str]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            charset: Optional[str] = None,
            max_length: Optional[int] = None,
            not_null: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "longtext",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class MediumTextField(Field[str]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            charset: Optional[str] = None,
            max_length: Optional[int] = None,
            not_null: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "mediumtext",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class DatetimeField(Field[datetime]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            max_length: Optional[int] = None,
            not_null: bool = False,
            created_generated: bool = False,
            update_generated: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "datetime",
                default,
                max_length=max_length,
                NOT_NULL=not_null,
                created_generated=created_generated,
                update_generated=update_generated,
                comment=comment,
            )

    class DateField(Field[date]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            max_length: Optional[int] = None,
            not_null: bool = False,
            created_generated: bool = False,
            update_generated: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "date",
                default,
                max_length=max_length,
                NOT_NULL=not_null,
                created_generated=created_generated,
                update_generated=update_generated,
                comment=comment,
            )

    class TimestampField(Field[datetime]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            max_length: Optional[int] = None,
            not_null: bool = False,
            created_generated: bool = False,
            update_generated: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "timestamp",
                default,
                False,
                max_length=max_length,
                NOT_NULL=not_null,
                created_generated=created_generated,
                update_generated=update_generated,
                comment=comment,
            )

    class JsonField(Field[Union[dict[str, Any], list[Any], str, int, float, bool]]):
        def __init__(
            self,
            name: Optional[str] = None,
            default: Optional[Any] = None,
            charset: Optional[str] = None,
            not_null: bool = False,
            comment: Optional[str] = None,
        ) -> None:
            super().__init__(
                name,
                "json",
                default,
                charset=charset,
                NOT_NULL=not_null,
                comment=comment,
            )


models = Models()
