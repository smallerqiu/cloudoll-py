import asyncio
from cloudoll.web import post
from pathlib import Path

@post("/api/upload", sa_ignore=True)
async def upload(ctx, file):
    """
    upload api
    """
    file_name = file.filename  # Get the file name
    file_content = await file.read()  # Get the file
    file_dir = Path("static") / "upload"  # Define the upload directory
    file_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it
    save_path = file_dir / file_name
    with open(save_path, "wb") as f:
        f.write(file_content)

    return {
        "message": "upload success",
        "file_name": file_name,
        "file_size": len(file_content),
    }
