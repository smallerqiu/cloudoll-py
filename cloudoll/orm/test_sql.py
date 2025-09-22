from model import models, Model


class A(Model):

    __table__ = "a"

    id = models.BigIntegerField(
        primary_key=True, max_length=64, not_null=True, comment="ID"
    )
    gmt_create = models.TimestampField(
        max_length=3, default="CURRENT_TIMESTAMP(3)", not_null=True, comment="time"
    )


class B(Model):

    __table__ = "b"

    id = models.BigIntegerField(primary_key=True, max_length=64, not_null=True)
    b1 = models.BigIntegerField(max_length=64, default="0", not_null=True)
    b2 = models.VarCharField(max_length=512, default="", not_null=True)
    b3 = models.IntegerField(max_length=16, default="0", not_null=True)
    b4 = models.VarCharField(max_length=512, default="", not_null=True)


class C(Model):

    __table__ = "c"

    id = models.BigIntegerField(primary_key=True, max_length=64, not_null=True)
    c1 = models.BigIntegerField(max_length=64, default="0", not_null=True)
    c2 = models.IntegerField(max_length=32, default="-1", not_null=True)
    c3 = models.IntegerField(max_length=32, default="-1", not_null=True)
    c4 = models.VarCharField(max_length=64, default="", not_null=True)
    c5 = models.VarCharField(max_length=32, default="", not_null=True)
    c6 = models.TimestampField(
        max_length=3, default="CURRENT_TIMESTAMP(3)", not_null=True
    )
    c7 = models.NumericField(max_length=12, scale_length=2, default="0", not_null=True)
    c8 = models.NumericField(max_length=12, scale_length=2, default="0", not_null=True)
    c9 = models.BooleanField(default="true", not_null=True)


def test_query():
    sql, arg = (
        B.use("")
        .select(
            B.b1.As("host_no"),
            B.b2.count().As("total_count"),
            C.c1.As("region"),
            C.c2.avg_when(C.c2 == False, C.c3).As("avg_val"),
            C.c3.min_when(C.c3 == False, C.c4).As("min_val"),
            C.c4.max_when(C.c4 == False, C.c5).As("max_val"),
            C.c5.sum_when(C.c5 == False, 1, 0).As("success_count"),
            C.c6.sum_when(C.c6 == True, 1, 0).As("failure_count"),
        )
        .join(C, C.c1 == B.id)
        .where(
            B.b1 == 1,
            B.b2 == int(1),
            B.b3.In(tuple(["aa"])),
        )
        .group_by(B.b2, C.c1)
        .test()
    )
    # sql = B()._exchange_sql(sql)
    print(sql, arg)


def test_a():
    role_id = ("5", 4, 7, 6, 0)
    sql, arg = (
        B.use("")
        .join(A, A.id == B.id)
        .where(
            # B.b1.In(role_id),
            B.b2 == 0,
            ((B.b2 != 1)|(B.b2 != "2")),
            # A.a1.In(role_id),
            A.id.between(1, 2),
            A.id.json_contains_object(A.id, "id"),
            A.id.json_contains_array(("3", "a","b","c","d")),
        )
        .test()
    )
    print(sql, arg)


if __name__ == "__main__":
    # test_query()
    test_a()
