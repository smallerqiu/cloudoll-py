import aiohttp
import asyncio
from aiohttp import BasicAuth, ClientSession


__all__ = ("Session", "BasicAuth")


class Session:
    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 1,
        retry_delay: int = 1,
        **kwargs,
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session: ClientSession = ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout), **kwargs
        )

    async def request(
        self,
        method: str,
        url: str,
        **kwargs,
    ):
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                response = await self.session.request(method=method, url=url, **kwargs)
                return response

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                continue
            # finally:
            #     if use_temp_session:
            #         await session.close()

        raise last_exception or RuntimeError(
            f"Request failed after {self.max_retries} attempts"
        )

    async def get(
        self,
        url: str,
        **kwargs,
    ):
        """Send a GET request"""
        return await self.request("GET", url, **kwargs)

    async def post(
        self,
        url: str,
        **kwargs,
    ):
        """Send a POST request"""
        return await self.request("POST", url, **kwargs)

    async def put(
        self,
        url: str,
        **kwargs,
    ):
        """Send a PUT request"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs):
        """Send a DELETE request"""
        return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        """Close the aiohttp session if it exists"""
        if self.session is not None:
            await self.session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()