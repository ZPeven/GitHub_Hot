"""
南京大学AI成果专项抓取器
"""

import asyncio
from bs4 import BeautifulSoup
from crawlers.base import BaseCrawler
from config import NJU_KEYWORDS


class NJUScraper(BaseCrawler):
    """南大AI成果专项 — 官网 + LAMDA实验室 + 搜索引擎"""

    NJU_SOURCES = [
        {
            "name": "NJU CS News",
            "url": "https://cs.nju.edu.cn/ai_news/list.htm",
            "type": "web",
        },
        {
            "name": "NJU AI School",
            "url": "https://ai.nju.edu.cn/ai_news/list.htm",
            "type": "web",
        },
        {
            "name": "LAMDA Group",
            "url": "https://www.lamda.nju.edu.cn/CH.Publication.ashx",
            "type": "web",
        },
    ]

    async def crawl(self) -> list[dict]:
        results = []

        # 并行抓取南大官网
        nju_tasks = [self._scrape_nju_site(s) for s in self.NJU_SOURCES]
        site_results = await asyncio.gather(*nju_tasks, return_exceptions=True)
        for r in site_results:
            if isinstance(r, list):
                results.extend(r)

        # arXiv 南大作者搜索
        arxiv_items = await self._search_arxiv_nju()
        results.extend(arxiv_items)

        return results

    async def _scrape_nju_site(self, source: dict) -> list[dict]:
        """抓取南大官网页面"""
        name = source["name"]
        url = source["url"]
        try:
            html = await self.fetch(url)
            if not html:
                return []

            soup = BeautifulSoup(html, "lxml")
            items = []

            # 南大网站常见结构
            for link in soup.select(".news_list a, .list_item a, .news_title a, li a"):
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not title or not href or len(title) < 6:
                    continue

                # 补全URL
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(url, href)

                items.append(self.make_item(
                    url=href,
                    title=title,
                    summary="",
                    source_name=name,
                    source_type="web",
                    category="nju",
                    is_nju=True,
                ))
                if len(items) >= 15:
                    break

            return items

        except Exception:
            return []

    async def _search_arxiv_nju(self) -> list[dict]:
        """在 arXiv 中搜索南大作者的最新论文"""
        import xml.etree.ElementTree as ET

        query = " OR ".join([f'all:"{kw}"' for kw in NJU_KEYWORDS[:3]])
        url = (
            f"http://export.arxiv.org/api/query?"
            f"search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results=10"
        )

        try:
            xml_text = await self.fetch(url)
            if not xml_text:
                return []

            root = ET.fromstring(xml_text)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }

            items = []
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                link = entry.find("atom:id", ns)
                authors = entry.findall("atom:author", ns)

                title_text = title.text.strip().replace("\n", " ") if title is not None else ""
                summary_text = summary.text.strip()[:300] if summary is not None else ""
                link_text = link.text.strip() if link is not None else ""
                author_list = [
                    a.find("atom:name", ns).text
                    for a in authors if a.find("atom:name", ns) is not None
                ]

                if not title_text or not link_text:
                    continue

                arxiv_id = link_text.split("/abs/")[-1] if "/abs/" in link_text else ""

                items.append(self.make_item(
                    url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else link_text,
                    title=f"[NJU] {title_text}",
                    summary=f"Authors: {', '.join(author_list[:5])} — {summary_text}"[:500],
                    source_name="NJU arXiv Search",
                    source_type="api",
                    category="nju",
                    is_nju=True,
                    authors=author_list,
                ))

            return items
        except Exception:
            return []
