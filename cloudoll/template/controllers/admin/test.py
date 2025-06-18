from cloudoll.web import get


@get("/admin/test")
async def home():
    return {"msg": "cloudoll"}
