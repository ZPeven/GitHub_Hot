"""
通用网页抓取器 — 处理已知网站 (非RSS)
"""

from bs4 import BeautifulSoup
from crawlers.base import BaseCrawler
from config import MAX_ITEMS_PER_RSS


class WebScraper(BaseCrawler):
    """通用Web抓取 — 根据源类型适配解析策略"""

    async def crawl(self, sources: list[dict]) -> list[dict]:
        results = []
        for src in sources:
            if src.get("type") != "web" or not src.get("enabled", True):
                continue
            items = await self._scrape(src)
            results.extend(items)
        return results

    async def _scrape(self, source: dict) -> list[dict]:
        url = source.get("url", "")
        name = source.get("name", "Unknown")
        tags = source.get("tags", [])

        try:
            html = await self.fetch(url)
            if not html:
                return []

            soup = BeautifulSoup(html, "lxml")

            # 根据标签选择解析策略
            if "zhihu" in tags:
                return self._parse_zhihu(soup, name)
            elif "juejin" in tags:
                return self._parse_juejin(soup, name, url)
            else:
                return self._parse_generic(soup, name, url)

        except Exception:
            return []

    def _parse_zhihu(self, soup: BeautifulSoup, name: str) -> list[dict]:
        """知乎热榜解析"""
        items = []
        cards = soup.select(".HotItem, .TopicHotItem, [data-za-detail-view-element_name='Title']")
        for card in cards[:MAX_ITEMS_PER_RSS]:
            link = card.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.zhihu.com" + href
            if not title or not href:
                continue

            # 摘要
            excerpt_el = card.select_one(".HotItem-excerpt, p")
            summary = excerpt_el.get_text(strip=True) if excerpt_el else ""

            items.append(self.make_item(
                url=href, title=title, summary=summary,
                source_name=name, source_type="web", category="community",
            ))
        return items

    def _parse_juejin(self, soup: BeautifulSoup, name: str, base_url: str) -> list[dict]:
        """掘金文章解析"""
        items = []
        articles = soup.select(".entry-list .item, .article-item, a.title")
        for art in articles[:MAX_ITEMS_PER_RSS]:
            link = art if art.name == "a" else art.select_one("a.title, a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = "https://juejin.cn" + href
            if not title or not href:
                continue

            items.append(self.make_item(
                url=href, title=title, summary="",
                source_name=name, source_type="web", category="community",
            ))
        return items

    def _parse_generic(self, soup: BeautifulSoup, name: str, base_url: str) -> list[dict]:
        """通用网页解析 — 提取所有可能的文章链接"""
        from urllib.parse import urljoin
        items = []
        # 常见文章容器选择器
        selectors = [
            "article a", ".post a.title", ".entry-title a", ".news-item a",
            ".list-item a", "h2 a", "h3 a", ".card a", ".item a.title-link",
            "a[rel='bookmark']", ".headline a",
        ]
        seen = set()
        for sel in selectors:
            for link in soup.select(sel):
                href = link.get("href", "")
                if not href or href.startswith("#") or href.startswith("javascript"):
                    continue
                title = link.get_text(strip=True)
                if not title or len(title) < 8:
                    continue
                full_url = urljoin(base_url, href)
                if full_url in seen:
                    continue
                seen.add(full_url)

                items.append(self.make_item(
                    url=full_url, title=title, summary="",
                    source_name=name, source_type="web", category="news",
                ))
                if len(items) >= MAX_ITEMS_PER_RSS:
                    return items
            if items:
                break
        return items
