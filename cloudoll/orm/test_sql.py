from model import models, Model


class A(Model):

    __table__ = "a"

    id = models.BigIntegerField(
        primary_key=True, max_length=64, not_null=True, comment="ID"
    )
    source = models.IntegerField(max_length=16, not_null=True, comment="状态")
    param = models.TextField(not_null=True)
    gmt_create = models.TimestampField(
        max_length=3, default="CURRENT_TIMESTAMP(3)", not_null=True, comment="创建时间"
    )


class B(Model):

    __table__ = "b"

    id = models.BigIntegerField(primary_key=True, max_length=64, not_null=True)
    task_id = models.BigIntegerField(max_length=64, default="0", not_null=True)
    employee_id = models.BigIntegerField(max_length=64, default="0", not_null=True)
    agency_id = models.BigIntegerField(max_length=64, default="0", not_null=True)
    proxy_str = models.VarCharField(max_length=512, default="", not_null=True)
    proxy_scheme = models.VarCharField(max_length=16, default="", not_null=True)
    proxy_ip = models.VarCharField(max_length=64, default="", not_null=True)
    proxy_region = models.VarCharField(max_length=32, default="", not_null=True)
    proxy_order_no = models.VarCharField(max_length=64, default="", not_null=True)
    proxy_merchant = models.VarCharField(max_length=32, default="", not_null=True)
    proxy_subnet = models.VarCharField(max_length=128, default="", not_null=True)
    channel_type = models.IntegerField(max_length=16, default="0", not_null=True)
    channel = models.VarCharField(max_length=512, default="", not_null=True)
    type = models.IntegerField(max_length=16, default="0", not_null=True)
    url = models.VarCharField(max_length=512, default="", not_null=True)
    gmt_create = models.TimestampField(
        max_length=3, default="CURRENT_TIMESTAMP(3)", not_null=True
    )
    timeout = models.IntegerField(max_length=32, default="0", not_null=True)


class C(Model):

    __table__ = "c"

    id = models.BigIntegerField(primary_key=True, max_length=64, not_null=True)
    pack_id = models.BigIntegerField(max_length=64, default="0", not_null=True)
    delay = models.IntegerField(max_length=32, default="-1", not_null=True)
    finish_load = models.IntegerField(max_length=32, default="-1", not_null=True)
    ip = models.VarCharField(max_length=64, default="", not_null=True)
    region = models.VarCharField(max_length=32, default="", not_null=True)
    gmt_create = models.TimestampField(
        max_length=3, default="CURRENT_TIMESTAMP(3)", not_null=True
    )
    speed = models.NumericField(
        max_length=12, scale_length=2, default="0", not_null=True
    )
    packet_loss_rate = models.NumericField(
        max_length=12, scale_length=2, default="0", not_null=True
    )
    is_failed = models.BooleanField(default="true", not_null=True)
    is_timeout = models.BooleanField(default="true", not_null=True)


if __name__ == "__main__":
    sql, arg = (
        B.use()
        .select(
            B.proxy_order_no.As("host_no"),
            B.proxy_order_no.count().As("total_count"),
            C.region.As("region"),
            C.is_failed.avg_when(C.is_failed == False, C.finish_load).As("avg_val"),
            C.is_failed.min_when(C.is_failed == False, C.finish_load).As("min_val"),
            C.is_failed.max_when(C.is_failed == False, C.finish_load).As("max_val"),
            C.is_failed.sum_when(C.is_failed == False, 1, 0).As("success_count"),
            C.is_failed.sum_when(C.is_failed == True, 1, 0).As("failure_count"),
        )
        .join(C, C.pack_id == B.id)
        .where(
            B.channel_type == 1,
            B.type == int(1),
            B.proxy_order_no.In(tuple(["aa"])),
        )
        .group_by(B.proxy_order_no, C.region)
        .test()
    )
    # sql = B()._exchange_sql(sql)
    print(sql, arg)
