

from cloudoll.web import get


@get("/admin/test")
async def home() -> dict[str, str]:
    return {"msg": "cloudoll"}
