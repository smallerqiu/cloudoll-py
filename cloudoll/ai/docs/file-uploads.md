---
title: 上传文件
order: 90
icon: upload
---

# 文件上传

## 表单与参数

```html
<form action="/upload" method="post" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button type="submit">上传</button>
</form>
```

二参数处理器 `async def upload(request, field)` 收到的是第一个 multipart 字段。非 multipart 请求返回 415，空 multipart 返回 400；第一个字段不一定是文件，业务必须检查 filename/name。多字段上传需要自行设计解析流程，不要假设自动注入全部文件。

## 限量流式保存

下面示例保存到应用根目录的私有 uploads 目录，不直接公开静态访问。部署者需要保证该目录及其父目录不允许不可信用户写入。

```python
# controllers/upload.py
import tempfile
from pathlib import Path
from uuid import uuid4
from aiohttp import web
from cloudoll.web import post

MAX_BYTES = 10 * 1024 * 1024

@post("/upload")
async def upload(request, field):
    if field.name != "file" or not field.filename:
        raise web.HTTPBadRequest(reason="Expected a file field")

    root = request.app.cloudoll_application.configuration.root
    directory = Path(root) / "uploads"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    upload_id = uuid4().hex
    target = directory / upload_id
    size = 0
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise web.HTTPRequestEntityTooLarge(
                        max_size=MAX_BYTES, actual_size=size
                    )
                output.write(chunk)
        temporary.replace(target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"id": upload_id, "size": size}
```

示例不使用客户端文件名作为路径，不给上传内容保留可执行扩展名；失败或取消时清理临时文件。例子采用小块同步磁盘写入以突出协议与大小限制；高并发生产应改用带背压、正确取消清理的异步存储/对象存储上传方案，避免磁盘阻塞事件循环。

```sh
curl -F 'file=@./example.txt' http://127.0.0.1:9001/upload
```

server.client_max_size 默认 2 MiB，适用于框架缓冲请求体的读取；不能据此省略流式 multipart 的累计大小检查。反向代理还应设置与业务一致的上传总大小、超时和速率限制。

生产必须补充登录鉴权、上传配额、内容类型/文件内容验证、恶意文件检查、私有下载授权和临时文件过期清理。客户端声明的 Content-Type、扩展名都不可信。

## 流式读取不等于断点续传

上例是一次 HTTP 请求内部逐块读取，不是多请求分片合并。不要把多个请求的数据按客户端 filename 用 ab+ 直接追加：重试、并发、乱序会造成重复数据和串文件。

真正的断点续传协议需要：

- 服务端签发上传 ID，并绑定用户、总大小、分片数和过期时间。
- 按 ID + 分片序号隔离暂存，每片校验长度和摘要，重复请求幂等。
- 完整校验后按序合并，核对最终摘要，再原子发布。
- 限制并发、磁盘配额，清理失败和过期上传。

Cloudoll 没有内置完整断点续传协议；应由业务或成熟对象存储方案实现。
