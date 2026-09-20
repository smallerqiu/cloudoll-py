"""Positive and negative field inference assertions (mypy only)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union

from cloudoll.orm.field import Expression, Field
from cloudoll.orm.model import Model, models
from cloudoll.orm.values import UNSET, _Unset


class Entry(Model):
    id = models.IntegerField(primary_key=True)
    label = models.VarCharField()
    active = models.BooleanField()
    amount = models.DecimalField()
    created = models.DatetimeField()
    day = models.DateField()


def contract(row: Entry) -> None:
    integer: Field[int] = Entry.id
    value: Union[int, None, _Unset] = row.id.value
    text: Union[str, None, _Unset] = row.label.value
    decimal: Union[Decimal, None, _Unset] = row.amount.value
    timestamp: Union[datetime, None, _Unset] = row.created.value
    day: Union[date, None, _Unset] = row.day.value
    condition: Expression = Entry.id == 1
    row.id = 2
    row.id = None
    row.id = UNSET
    row.id.value = 3
    row.label = "typed"
    row.active = True
    row.amount = Decimal("1.23")
    row.id = "wrong"  # type: ignore[assignment]
    row.id.value = "wrong"  # type: ignore[assignment]
    row.label = 3  # type: ignore[assignment]
    wrong: Optional[str] = row.id.value  # type: ignore[assignment]
    wrong_field: Field[str] = Entry.id  # type: ignore[assignment]
