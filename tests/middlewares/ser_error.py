import cloudoll.web as web
from cloudoll.web import middleware, view
from cloudoll import logging


async def handle_404():
    return view("404.html", {"message": "Please try again!"}, status=404)


async def handle_500():
    return view("500.html", {"message": "Something went wrong."}, status=500)


@middleware()
def mid_error():
    async def error(request, handler):
        try:
            return await handler(request)
        except web.HTTPMethodNotAllowed or web.HTTPNotFound:
            # return render(status=404, text="The url not found.") for Restful api
            return await handle_404()
        except Exception as e:
            logging.error(e)
            # return render(status=500, text="Something went wrong.") for Restful api
            return await handle_500()

    return error
