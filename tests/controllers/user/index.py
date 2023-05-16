from cloudoll.web import render, get, post, delete, put


@get('/user/{id}')
async def user_page(request):
    body = f"Hello {request.params.id}"
    return render(body=body)


@post('/user/{id}')
async def user_post(request):
    body = f"Hello {request.params.id}"
    return render(body=body)


@delete('/user/{id}')
async def user_delete(request):
    body = f"Hello {request.params.id}"
    return render(body=body)


@put('/user/{id}')
async def user_put(request):
    body = f"Hello {request.params.id}"
    return render(body=body)
