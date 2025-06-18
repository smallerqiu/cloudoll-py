import aiohttp
import asyncio
from typing import Optional, Dict, Any, Union


class AsyncRequest:
    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        """
        Asynchronous HTTP request client

        :param timeout: Request timeout(Second)
        :param max_retries: Maximum retry attempts
        :param retry_delay: Retry delay(Second)
        :param session: Reusable aiohttp session
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session = session

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        allow_redirects: bool = True,
        raise_for_status: bool = True,
    ) -> aiohttp.ClientResponse:
        """
        Perform asynchronous HTTP requests

        :param method: HTTP方法 (GET, POST, PUT, DELETE等)
        :param url: Request URL
        :param params: URL query parameters
        :param data: Request body data (Forms or raw data)
        :param json_data: JSON formatted request body data
        :param headers: Request headers
        :param cookies: Cookies
        :param allow_redirects: Whether to allow redirects
        :param raise_for_status: Whether to raise an exception for HTTP errors
        :return: aiohttp.ClientResponse
        """
        session = self._session or aiohttp.ClientSession(timeout=self.timeout)
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                async with session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json_data,
                    headers=headers,
                    cookies=cookies,
                    allow_redirects=allow_redirects,
                ) as response:
                    if raise_for_status:
                        response.raise_for_status()
                    return response

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                continue

        if self._session is None:
            await session.close()

        raise last_exception or RuntimeError("Request failed")

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """Send a GET request"""
        return await self.request("GET", url, params=params, headers=headers, **kwargs)

    async def post(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """Send a POST request"""
        return await self.request(
            "POST", url, data=data, json_data=json_data, headers=headers, **kwargs
        )

    async def put(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """Send a PUT request"""
        return await self.request(
            "PUT", url, data=data, json_data=json_data, headers=headers, **kwargs
        )

    async def delete(
        self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> aiohttp.ClientResponse:
        """Send a DELETE request"""
        return await self.request("DELETE", url, headers=headers, **kwargs)

    async def close(self) -> None:
        """Close the aiohttp session if it exists """
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# demo
"""
async def test():
    async with AsyncRequest() as client:
        try:
            # GET Request example
            response = await client.get(
                "https://httpbin.org/get",
                params={"key": "value"},
                headers={"User-Agent": "AsyncRequest/1.0"},
            )
            print(await response.json())

            # POST Request example
            response = await client.post(
                "https://httpbin.org/post",
                json_data={"key": "value"},
                headers={"Content-Type": "application/json"},
            )
            print(await response.json())

        except Exception as e:
            print(f"Request failed: {e}")
"""
