import aiohttp
import asyncio
# import ssl
from typing import Optional, Dict, Union, List, Any

JSONType = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


class AsyncRequest:
    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 1,
        retry_delay: float = 1.0,
        keep_alive: bool = True,
        use_cookies: bool = False,
        proxy: Optional[str] = None,
        # session: Optional[aiohttp.ClientSession] = None,
        # connector: Optional[aiohttp.BaseConnector] = None,
        # ssl: Union[bool, ssl.SSLContext] = True,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        # self.session = session
        # self.connector = connector
        self.use_cookies = use_cookies
        self.keep_alive = keep_alive
        
        self.session = aiohttp.ClientSession(
            proxy=proxy,
            connector=aiohttp.TCPConnector(keepalive_timeout=self.timeout) if self.keep_alive else None,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            cookie_jar=aiohttp.CookieJar() if self.use_cookies else None,
        )

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[JSONType] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        allow_redirects: bool = True,
        raise_for_status: bool = True,
        proxy: Optional[str] = None,
        # parse_json: bool = False,
    ) -> Union[dict, str, aiohttp.ClientResponse]:
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                response  = await self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json_data,
                    headers=headers,
                    cookies=cookies,
                    allow_redirects=allow_redirects,
                    proxy=proxy,
                ) 
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
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Send a GET request"""
        return await self.request("GET", url, params=params, headers=headers, **kwargs)

    async def post(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
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
        **kwargs,
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
        """Close the aiohttp session if it exists"""
        if self.session is not None and not self.keep_alive:
            await self.session.close()
            self.session = None

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
