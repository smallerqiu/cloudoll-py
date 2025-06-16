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
        异步HTTP请求客户端

        :param timeout: 请求超时时间(秒)
        :param max_retries: 最大重试次数
        :param retry_delay: 重试延迟(秒)
        :param session: 可复用的aiohttp会话
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
        执行异步HTTP请求

        :param method: HTTP方法 (GET, POST, PUT, DELETE等)
        :param url: 请求URL
        :param params: URL查询参数
        :param data: 请求体数据 (表单或原始数据)
        :param json_data: JSON格式的请求体数据
        :param headers: 请求头
        :param cookies: cookies
        :param allow_redirects: 是否允许重定向
        :param raise_for_status: 是否在HTTP错误状态时抛出异常
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
        """发送GET请求"""
        return await self.request("GET", url, params=params, headers=headers, **kwargs)

    async def post(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """发送POST请求"""
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
        """发送PUT请求"""
        return await self.request(
            "PUT", url, data=data, json_data=json_data, headers=headers, **kwargs
        )

    async def delete(
        self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> aiohttp.ClientResponse:
        """发送DELETE请求"""
        return await self.request("DELETE", url, headers=headers, **kwargs)

    async def close(self) -> None:
        """关闭客户端会话"""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 使用示例
"""
async def test():
    async with AsyncRequest() as client:
        try:
            # GET请求示例
            response = await client.get(
                "https://httpbin.org/get",
                params={"key": "value"},
                headers={"User-Agent": "AsyncRequest/1.0"},
            )
            print(await response.json())

            # POST请求示例
            response = await client.post(
                "https://httpbin.org/post",
                json_data={"key": "value"},
                headers={"Content-Type": "application/json"},
            )
            print(await response.json())

        except Exception as e:
            print(f"Request failed: {e}")
"""
