"""Opt-in real Aurora failover recovery. Never runs in normal CI.

Requires an explicitly authorized dedicated test cluster and AWS credentials.
"""
import asyncio
import json
import os
import time

import pytest

from cloudoll.orm import create_engine


@pytest.mark.aws_failover
@pytest.mark.integration
async def test_aurora_failover_recovers_queries():
    cluster_id = os.getenv("CLOUDOLL_AWS_TEST_CLUSTER")
    if not cluster_id or os.getenv("CLOUDOLL_ALLOW_FAILOVER") != cluster_id:
        pytest.skip("Failover requires explicit authorization for a dedicated test cluster")
    boto3 = pytest.importorskip("boto3")
    region = os.environ["CLOUDOLL_AWS_TEST_REGION"]
    config = json.loads(os.environ["CLOUDOLL_AWS_TEST_DB_CONFIG"])
    assert config.get("type") in {"aws-mysql", "aws-postgres"}
    assert "url" not in config, "Use structured AWS driver configuration"
    rds = boto3.client("rds", region_name=region)

    async def cluster():
        response = await asyncio.to_thread(rds.describe_db_clusters, DBClusterIdentifier=cluster_id)
        return response["DBClusters"][0]

    def writer(value):
        return next(member["DBInstanceIdentifier"] for member in value["DBClusterMembers"] if member["IsClusterWriter"])

    before = await cluster()
    assert before["Engine"] in {"aurora-mysql", "aurora-postgresql"}
    assert before["Status"] == "available" and len(before["DBClusterMembers"]) >= 2
    assert config["host"] == before["Endpoint"], "Use the selected cluster's writer endpoint"
    engine = await create_engine(**config)
    try:
        assert (await engine.one("SELECT 1 AS value", None))["value"] == 1
        await asyncio.to_thread(rds.failover_db_cluster, DBClusterIdentifier=cluster_id)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            current = await cluster()
            if writer(current) != writer(before) and current["Status"] == "available":
                try:
                    result = await engine.one("SELECT 1 AS value", None)
                except Exception:
                    pass  # DNS/connection recovery can lag behind the RDS control plane.
                else:
                    assert result["value"] == 1
                    return
            await asyncio.sleep(5)
        pytest.fail("Writer did not change and recover queries within 300 seconds")
    finally:
        await engine.close()
