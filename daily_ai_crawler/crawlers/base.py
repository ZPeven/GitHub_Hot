"""
爬虫基类 — 提供通用HTTP请求能力
"""

import time
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from config import (
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY,
    USER_AGENT, PROXIES, POLITE_DELAY,
)


class BaseCrawler(ABC):
    """所有爬虫的抽象基类"""

    def __init__(self, session: aiohttp.ClientSession = None):
        self.session = session
        self._own_session = False
        self._last_request_time = 0

    async def _ensure_session(self):
        if self.session is None:
            connector = aiohttp.TCPConnector(limit=5, force_close=True)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            )
            self._own_session = True

    async def close(self):
        if self._own_session and self.session:
            await self.session.close()

    async def _polite_wait(self):
        """礼貌延迟"""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < POLITE_DELAY:
            await asyncio.sleep(POLITE_DELAY - elapsed)
        self._last_request_time = time.monotonic()

    async def fetch(self, url: str, **kwargs) -> str | None:
        """带重试的HTTP GET请求"""
        await self._ensure_session()
        await self._polite_wait()

        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", USER_AGENT)
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)

        # 使用代理
        if PROXIES:
            kwargs["proxy"] = PROXIES["http"]

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with self.session.get(url, headers=headers, **kwargs) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    elif resp.status == 429:
                        wait = int(resp.headers.get("Retry-After", RETRY_DELAY * (attempt + 1)))
                        await asyncio.sleep(wait)
                    elif resp.status >= 500:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        return None
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return None
        return None

    async def fetch_json(self, url: str, **kwargs) -> dict | None:
        """获取JSON响应"""
        await self._ensure_session()
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", USER_AGENT)
        if PROXIES:
            kwargs["proxy"] = PROXIES["http"]

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with self.session.get(url, headers=headers, **kwargs) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        wait = int(resp.headers.get("Retry-After", RETRY_DELAY * (attempt + 1)))
                        await asyncio.sleep(wait)
                    else:
                        await asyncio.sleep(RETRY_DELAY)
            except Exception:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return None
        return None

    @abstractmethod
    async def crawl(self) -> list[dict]:
        """执行抓取，返回标准化条目列表"""
        ...

    @staticmethod
    def make_item(url: str, title: str, summary: str = "",
                  source_name: str = "", source_type: str = "",
                  category: str = "", **kwargs) -> dict:
        return {
            "url": url,
            "title": title.strip(),
            "summary": summary.strip()[:500],
            "source_name": source_name,
            "source_type": source_type,
            "category": category,
            **kwargs,
        }
