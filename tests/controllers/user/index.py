from cloudoll.web import render, get, post, delete, put, jsons
from tests.services.user import get_user_by_id


@get('/user/{id}')
async def user_page(request):
    body = f"Hello {request.params.id}"
    user = await  get_user_by_id()
    return jsons(user)
    # return render(body=body)


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
