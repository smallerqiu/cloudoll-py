from copy import deepcopy

from cloudoll.orm import UNSET
from cloudoll.orm.model import Model, models


class TypedRecord(Model):
    id = models.IntegerField(primary_key=True)
    name = models.VarCharField(not_null=True)


def test_field_descriptors_preserve_record_isolation_and_copy():
    first, second = TypedRecord(id=1), TypedRecord(id=2)
    first.name = "one"
    assert first.name.value == "one"
    assert second.name.value is UNSET
    assert TypedRecord.name.value is None
    cloned = deepcopy(first)
    cloned.name.value = "copy"
    assert first.name.value == "one"
    assert cloned.to_dict() == {"id": 1, "name": "copy"}
    first.name = None
    assert first.name.value is None
    first.name = UNSET
    assert first.to_dict(exclude_unset=True) == {"id": 1}


def test_not_null_keyword_is_not_silently_discarded():
    assert models.CharField(not_null=True).NOT_NULL is True
    assert models.VarCharField(not_null=True).NOT_NULL is True
    assert models.BooleanField(not_null=True).NOT_NULL is True
    assert models.IntegerField(not_null=True).NOT_NULL is True
    assert models.BigIntegerField(not_null=True).NOT_NULL is True
