from cloudoll.web import post, view, get, render, jsons
import os


# for Server api
@post('/upload-file')
async def upload_handle(request):
    data = request.body
    mp3_file = data.mp3

    file_name = mp3_file.filename
    file = mp3_file.file

    # 文件保存在 static/upload 目录
    save_path = os.path.join(os.path.abspath('.'), 'static/upload', file_name)
    with open(save_path, 'wb') as f:
        f.write(file.read())

    return render(body='上传成功')


# for Server api
@post('/upload-big-file')
async def upload_bigfile_handle(request, multipart):
    file_name = multipart.filename
    size = 0
    save_path = os.path.join(os.path.abspath('.'), 'static/upload', file_name)

    with open(save_path, 'ab+') as f:
        while True:
            chunk = await multipart.read_chunk()  # 8192 bytes by default.
            if not chunk:
                break
            size += len(chunk)
            f.write(chunk)
    return jsons({'msg': '上传成功', 'size': size})


# for Client router
@get('/upload')
async def upload_handle():
    return view('upload.html')
