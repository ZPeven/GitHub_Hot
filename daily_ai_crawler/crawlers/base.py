"""
爬虫基类 — 提供通用HTTP请求能力，内置 robots.txt 合规检查
"""

import time
import asyncio
import aiohttp
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from abc import ABC, abstractmethod
from config import (
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY,
    USER_AGENT, PROXIES, POLITE_DELAY,
)

# ── robots.txt 缓存（按域名，进程级）──────────
_robots_cache: dict[str, RobotFileParser | None] = {}


def _get_robots(url: str) -> RobotFileParser | None:
    """获取域名的 robots.txt 解析器（带缓存）"""
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"

    if domain in _robots_cache:
        return _robots_cache[domain]

    try:
        rp = RobotFileParser()
        rp.set_url(f"{domain}/robots.txt")
        rp.read()
        _robots_cache[domain] = rp
        return rp
    except Exception:
        _robots_cache[domain] = None
        return None


def is_allowed(url: str, user_agent: str = "AICrawler") -> bool:
    """
    检查 URL 是否被 robots.txt 允许爬取。
    如果 robots.txt 不可用，默认允许（但限制频率）。
    API 端点（api.*）和 RSS feed 默认视为允许。
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # API 域名通常明确允许程序访问
    if any(h in host for h in ["api.", "export.", "feed."]):
        return True

    # 检查 robots.txt
    rp = _get_robots(url)
    if rp is None:
        return True  # 无法获取 robots.txt → 允许但受限

    return rp.can_fetch(user_agent, url)


class BaseCrawler(ABC):
    """所有爬虫的抽象基类 — 内置礼貌爬取与 robots.txt 合规"""

    def __init__(self, session: aiohttp.ClientSession = None):
        self.session = session
        self._own_session = False
        self._last_request_time = 0
        self._domain_last_request: dict[str, float] = {}

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

    async def _polite_wait(self, url: str = ""):
        """基于域名的礼貌延迟（同域名至少间隔POLITE_DELAY秒）"""
        domain = urlparse(url).netloc if url else "default"
        now = time.monotonic()
        last = self._domain_last_request.get(domain, 0)
        if now - last < POLITE_DELAY:
            await asyncio.sleep(POLITE_DELAY - (now - last))
        self._domain_last_request[domain] = time.monotonic()

    async def fetch(self, url: str, **kwargs) -> str | None:
        """带重试和 robots.txt 检查的 HTTP GET"""
        # robots.txt 合规检查
        if not is_allowed(url):
            return None

        await self._ensure_session()
        await self._polite_wait(url)

        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", USER_AGENT)
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)

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
                    elif resp.status == 403:
                        return None  # 明确禁止，不重试
                    elif resp.status >= 500:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        return None
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError):
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return None
        return None

    async def fetch_json(self, url: str, **kwargs) -> dict | None:
        """带重试的 JSON API 请求"""
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
                    elif resp.status == 403:
                        return None
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
