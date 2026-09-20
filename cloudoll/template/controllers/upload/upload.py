from pathlib import Path
from typing import Any
from uuid import uuid4

from aiohttp import BodyPartReader, web

from cloudoll.web import post


@post("/api/upload", sa_ignore=True)
async def upload(ctx: web.Request, file: BodyPartReader) -> dict[str, Any]:
    """
    upload api
    """
    if not file.filename:
        raise web.HTTPBadRequest(reason="Expected a file name")
    # Never use a client-controlled path or overwrite another upload.
    file_name = uuid4().hex + Path(file.filename).suffix
    file_content = await file.read()  # Get the file
    file_dir = Path("static") / "upload"  # Define the upload directory
    file_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it
    save_path = file_dir / file_name
    with open(save_path, "xb") as f:
        f.write(file_content)

    return {
        "message": "upload success",
        "file_name": file_name,
        "file_size": len(file_content),
    }
