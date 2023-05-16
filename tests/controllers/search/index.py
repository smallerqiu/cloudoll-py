from cloudoll.web import render, get, post
import json


@get('/search')
async def search_page(request):
    body = f"My name is  {request.qs.name}"
    return render(body=body)


@post('/search')
async def search_post(request):
    body = f"body: {json.dumps(request.body)}"
    return render(body=body)
