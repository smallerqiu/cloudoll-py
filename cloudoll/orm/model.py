import copy
from typing import Any, Optional

from cloudoll.logging import warning
from cloudoll.orm.field import Field

__all__ = ("models", "Model")


class ModelMetaclass(type):
    # def __init__(self, **kw):
    #     pass
    # def __call__(cls, *args, **kwargs):
    #     instance = super().__call__(*args, **kwargs)
    #     # 在元类中处理拷贝逻辑
    #     return copy.copy(instance)

    def __new__(mcs, name, bases, attrs):
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
                        warning(f"Duplicate primary key for {table_name}")
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

    def __repr__(self):
        return "<Model: %s>" % self.__name__

    # def __getattr__(self, name):
    #     return self.__fields__[name]


class Model(metaclass=ModelMetaclass):
    __table__: str
    __primary_key__: Optional[str]
    __fields__: list

    def __init__(self, **kw):
        for k in self.__fields__:
            f = copy.copy(getattr(type(self), k))
            f.value = None
            object.__setattr__(self, k, f)
        for k, v in kw.items():
            self[k] = v

        # super().__init__(self, **kw)

    def __str__(self):
        return "<Model: %s>" % self.__class__.__name__

    def __repr__(self):
        return "<Model: %s>" % self.__class__.__name__

    def to_dict(self):
        _dict = {}
        for key in self.__fields__:
            f = getattr(self, key)
            _dict[key] = f.value
        return _dict

    # class to fun for cls(**)
    def __call__(self, **kw):
        self.__init__(**kw)

        return self

    def __getitem__(self, name):
        return getattr(self, name)

    # # .['x']
    def __setitem__(self, name, value):
        setattr(self, name, value)

    def __setattr__(self, name, value):
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
    def get(self, k, d=None):
        f = getattr(self, k, None)
        if isinstance(f, Field):
            return d if f.value is None else f.value
        return d if f is None else f

    def _get_primary(self):
        pk = self.__primary_key__
        if pk is None:
            return None, None
        pkf = getattr(self, pk)
        return pk, pkf.value

    @classmethod
    def use(cls, pool):
        from cloudoll.orm.query import Query
        return Query(cls, pool)

    def bind(self, pool):
        """Bind this record for subsequent update/delete/insert operations."""
        self._bound_pool = pool
        return self

    def __getattr__(self, name):
        # Compatibility facade: query operations live in Query, not in records.
        if name in {
            "select", "where", "having", "join", "order_by", "group_by",
            "limit", "offset", "test", "one", "all", "count",
            "insert", "insert_batch", "update", "delete",
        }:
            from cloudoll.orm.query import Query
            pool = self.__dict__.get("_bound_pool")
            return getattr(Query(type(self), pool, record=self), name)
        raise AttributeError(name)


class Models(object):
    class CharField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
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

    class VarCharField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
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

    class BooleanField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = False,
            not_null=False,
            comment=None,
            unsigned=False,
        ):
            super().__init__(
                name,
                "boolean",
                default,
                not_null=not_null,
                unsigned=unsigned,
                comment=comment,
            )

    class IntegerField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default: Optional[Any] = None,
            auto_increment=False,
            not_null=False,
            unsigned=False,
            comment=None,
            max_length=None,
        ):
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

    class BigIntegerField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default: Optional[Any] = None,
            auto_increment=False,
            not_null=False,
            unsigned=False,
            comment=None,
            max_length=None,
        ):
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

    class DoubleField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            not_null=False,
            max_length=None,
            unsigned=False,
            comment=None,
        ):
            super().__init__(
                name,
                "double",
                default,
                NOT_NULL=not_null,
                max_length=max_length,
                unsigned=unsigned,
                comment=comment,
            )

    class FloatField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            not_null=False,
            max_length=None,
            scale_length=None,
            unsigned=False,
            comment=None,
        ):
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

    class NumericField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = 0.0,
            not_null=False,
            max_length=None,
            scale_length=None,
            unsigned=False,
            comment=None,
        ):
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

    class DecimalField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = 0.0,
            not_null=False,
            max_length=None,
            scale_length=None,
            unsigned=False,
            comment=None,
        ):
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

    class TextField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "text",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class LongTextField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "longtext",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class MediumTextField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "mediumtext",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class DatetimeField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            max_length=None,
            not_null=False,
            created_generated=False,
            update_generated=False,
            comment=None,
        ):
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

    class DateField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            max_length=None,
            not_null=False,
            created_generated=False,
            update_generated=False,
            comment=None,
        ):
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

    class TimestampField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            max_length=None,
            not_null=False,
            created_generated=False,
            update_generated=False,
            comment=None,
        ):
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

    class JsonField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            charset=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "json",
                default,
                charset=charset,
                NOT_NULL=not_null,
                comment=comment,
            )


models = Models()
