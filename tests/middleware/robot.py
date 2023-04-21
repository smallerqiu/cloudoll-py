from cloudoll.web.server import middleware, render
import re


def mid_robot():
    @middleware
    async def robot(request, handler):
        ua = request.headers.get('user-agent')
        if re.match('Baiduspider', ua):
            return render(status=403, text="Go away , robot.")
        return await handler(request)

    return robot
