from cloudoll.web import middleware, render
import re


@middleware()
def mid_robot():
    async def robot(request, handler):
        ua = request.headers.get('user-agent', "")
        if re.match('Baiduspider', ua):
            return render(status=403, text="Go away , robot.")
        return await handler(request)

    return robot
