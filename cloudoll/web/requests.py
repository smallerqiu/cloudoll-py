from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Optional

import aiohttp
from aiohttp import BasicAuth, ClientSession

__all__ = ("Session", "BasicAuth")


def _replayable_body(value: Any) -> bool:
    """Only retry data that aiohttp can encode afresh without consuming a stream."""
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return True
    if isinstance(value, Mapping):
        return all(
            _replayable_body(key) and _replayable_body(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(_replayable_body(item) for item in value)
    return False


class Session:
    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 1,
        retry_delay: int = 1,
        retry_non_idempotent: bool = False,
        **kwargs: Any,
    ) -> None:
        if not isinstance(max_retries, int) or max_retries < 1:
            raise ValueError(
                "max_retries is the total number of attempts and must be >= 1"
            )
        if retry_delay < 0:
            raise ValueError("retry_delay must be >= 0")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_non_idempotent = retry_non_idempotent
        self.session: ClientSession = ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout), **kwargs
        )

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        last_exception = None

        method = method.upper()
        attempts = self.max_retries
        if not _replayable_body(kwargs.get("data")):
            # Files, generators, FormData and Payload objects can be consumed/closed
            # even when a request fails. Never silently send an empty second body.
            attempts = 1
        if not self.retry_non_idempotent and method not in {
            "GET",
            "HEAD",
            "OPTIONS",
            "PUT",
            "DELETE",
            "TRACE",
        }:
            attempts = 1
        for attempt in range(attempts):
            try:
                response = await self.session.request(method=method, url=url, **kwargs)
                return response

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < attempts - 1:
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
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Send a GET request"""
        return await self.request("GET", url, **kwargs)

    async def post(
        self,
        url: str,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Send a POST request"""
        return await self.request("POST", url, **kwargs)

    async def put(
        self,
        url: str,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Send a PUT request"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Send a DELETE request"""
        return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        """Close the aiohttp session if it exists"""
        if self.session is not None:
            await self.session.close()

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()
