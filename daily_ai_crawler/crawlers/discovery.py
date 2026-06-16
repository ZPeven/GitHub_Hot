"""
陌生网站发现爬虫 — 通过Bing News搜索发现AI热点来源
"""

import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from crawlers.base import BaseCrawler
from config import MAX_ITEMS_PER_DISCOVERY, MAX_ITEMS_PER_SEARCH


class DiscoveryCrawler(BaseCrawler):
    """搜索引擎发现 — 发现不在数据库中的新来源"""

    async def crawl(self, queries: list[dict]) -> list[dict]:
        """通过多个搜索查询发现新内容"""
        results = []

        tasks = [self._search_bing_news(q) for q in queries]
        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in search_results:
            if isinstance(r, list):
                results.extend(r)

        return results

    async def _search_bing_news(self, query_config: dict) -> list[dict]:
        """Bing News RSS搜索"""
        import urllib.parse
        import feedparser

        query = query_config.get("query", "")
        max_results = query_config.get("max_results", MAX_ITEMS_PER_SEARCH)

        encoded = urllib.parse.quote(query)
        url = f"https://www.bing.com/news/search?q={encoded}&format=rss"
        label = f"Bing: {query[:30]}"

        try:
            html = await self.fetch(url)
            if not html:
                return []

            feed = feedparser.parse(html)
            if not feed.entries:
                return []

            items = []
            for entry in feed.entries[:max_results]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not title or not link:
                    continue

                summary = ""
                if entry.get("summary"):
                    soup = BeautifulSoup(entry.summary, "lxml")
                    summary = soup.get_text(" ", strip=True)[:500]

                # 提取域名
                domain = urlparse(link).netloc

                items.append(self.make_item(
                    url=link,
                    title=title,
                    summary=summary,
                    source_name=label,
                    source_type="search",
                    category="news",
                    domain=domain,
                    is_discovered=True,
                ))

            return items

        except Exception:
            return []

    async def discover_and_fetch(self, url: str) -> dict | None:
        """对陌生URL进行通用内容提取"""
        try:
            html = await self.fetch(url)
            if not html:
                return None

            soup = BeautifulSoup(html, "lxml")

            # 提取标题
            title = ""
            for tag in ["h1", "h2", ".article-title", ".post-title", "title"]:
                el = soup.select_one(tag)
                if el:
                    title = el.get_text(strip=True)
                    break

            # 提取正文摘要
            summary = ""
            for tag in ["article p", ".article-content p", ".post-content p", ".content p", "p"]:
                paragraphs = soup.select(tag)[:5]
                if paragraphs:
                    summary = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)
                    if summary:
                        break
            summary = summary[:500]

            # 提取元数据
            meta_desc = soup.select_one("meta[name='description']")
            if meta_desc and not summary:
                summary = meta_desc.get("content", "")[:500]

            return {
                "url": url,
                "title": title,
                "summary": summary,
                "domain": urlparse(url).netloc,
            }

        except Exception:
            return None
