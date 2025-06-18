import asyncio
from cloudoll.logging import warning

EADDRINUSE: int


class Object(dict):
    # __setattr__ = dict.__setitem__
    # __getattr__ = dict.__getitem__
    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        return self.get(key, None)

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"'DotDict' object has no attribute '{key}'")

    def __getstate__(self):
        """to fix pickle.dumps"""
        return dict(self)

    def __setstate__(self, state):
        self.update(state)


def chainMap(*dicts):
    merged_dict = Object()
    for d in dicts:
        for key, value in d.items():
            if key not in merged_dict or value is not None:
                merged_dict[key] = value
    return merged_dict


async def check_port_open(port: int, delay: float = 1) -> None:
    loop = asyncio.get_running_loop()
    # the "s = socket.socket; s.bind" approach sometimes says a port is in use when it's not
    # this approach replicates aiohttp so should always give the same answer
    for i in range(5, 0, -1):
        try:
            server = await loop.create_server(
                asyncio.Protocol, host="0.0.0.0", port=port
            )
        except OSError as e:
            if e.errno != EADDRINUSE:
                raise
            warning("port %d is already in use, waiting %d...", port, i)
            await asyncio.sleep(delay)
        else:
            server.close()
            await server.wait_closed()
            return
    raise Exception("The port {} is already is use".format(port))
