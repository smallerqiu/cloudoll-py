from cloudoll.web.server import render, get, post
import json


@get('/search')
async def search_page(request, form):
    body = f"My name is  {form['name']}"
    return render(body=body)


@get('/search/{id}/{name}')
async def search_page(request):
    body = f"user:  {request.params['id']} , {request.params['name']}"
    return render(body=body)


@post('/search')
async def search_post(request, form):
    body = f"body: {json.dumps(form)}"
    return render(body=body)
