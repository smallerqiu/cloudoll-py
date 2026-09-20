"""Check actual native engines against the advertised structural interfaces."""

from cloudoll.orm.mysql import Mysql
from cloudoll.orm.postgres import Postgres
from cloudoll.orm.protocols import StreamingEngine, TransactionalEngine


async def contracts(mysql: Mysql, postgres: Postgres) -> None:
    transaction: TransactionalEngine = mysql
    transaction = postgres
    streaming: StreamingEngine = mysql
    streaming = postgres
    async with mysql.transaction() as outer:
        native: Mysql = outer
        async with mysql.savepoint() as inner:
            native = inner
