"""
RSS/Atom 订阅源抓取器
"""

import feedparser
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from crawlers.base import BaseCrawler
from config import MAX_ITEMS_PER_RSS


class RSSFetcher(BaseCrawler):
    """RSS 订阅源统一抓取"""

    async def crawl(self, sources: list[dict]) -> list[dict]:
        """并行抓取多个RSS源"""
        results = []
        for src in sources:
            if src.get("type") != "rss" or not src.get("enabled", True):
                continue
            items = await self._fetch_rss(src)
            results.extend(items)
        return results

    async def _fetch_rss(self, source: dict) -> list[dict]:
        """抓取单个RSS源"""
        url = source.get("url", "")
        name = source.get("name", "Unknown RSS")
        try:
            html = await self.fetch(url)
            if not html:
                return []

            feed = feedparser.parse(html)
            if feed.bozo and not feed.entries:
                return []

            items = []
            for entry in feed.entries[:MAX_ITEMS_PER_RSS]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not title or not link:
                    continue

                # 提取摘要
                summary = ""
                if entry.get("summary"):
                    soup = BeautifulSoup(entry.summary, "lxml")
                    summary = soup.get_text(" ", strip=True)[:500]
                elif entry.get("description"):
                    soup = BeautifulSoup(entry.description, "lxml")
                    summary = soup.get_text(" ", strip=True)[:500]

                # 提取发布时间
                published = ""
                if entry.get("published"):
                    try:
                        dt = parsedate_to_datetime(entry.published)
                        published = dt.isoformat()
                    except Exception:
                        pass

                # 提取标签
                tags = []
                if entry.get("tags"):
                    tags = [t.get("term", "") for t in entry.tags if t.get("term")]

                items.append(self.make_item(
                    url=link,
                    title=title,
                    summary=summary,
                    source_name=name,
                    source_type="rss",
                    category=source.get("category", "news"),
                    published=published,
                    tags=tags,
                ))

            return items

        except Exception as e:
            return []
