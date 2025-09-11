from cloudoll.orm import create_engine
import asyncio


async def test():
    pool = await create_engine(
        host="devops-cluster-eu.cluster-cf06dgja7nov.eu-central-1.rds.amazonaws.com",
        password="",
        plugins="iam",
        wrapper_dialect="aurora-mysql",
        user="service-devops-cicd",
        database="CICD",
        type="aws-mysql",
    )
    result = await pool.query("SELECT * from account limit 10")
    print(result)


if __name__ == "__main__":
    asyncio.run(test())
