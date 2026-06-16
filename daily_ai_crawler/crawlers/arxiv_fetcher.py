"""
arXiv API 论文抓取器
"""

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from crawlers.base import BaseCrawler
from config import MAX_ITEMS_PER_ARXIV, DOMAIN_KEYWORDS
from processors.lamda_matcher import check_nju


class ArxivFetcher(BaseCrawler):
    """arXiv 学术论文抓取 — 按分类 + 南大作者过滤"""

    async def crawl(self) -> list[dict]:
        """并行抓取 arXiv 多个分类（4个分类同时请求，避免串行超时）"""
        categories = ["cs.AI", "cs.LG", "cs.CL", "cs.MA"]
        tasks = [self._fetch_category(cat) for cat in categories]
        cat_results = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for r in cat_results:
            if isinstance(r, list):
                results.extend(r)
        return results

    async def _fetch_category(self, cat: str) -> list[dict]:
        url = (
            f"http://export.arxiv.org/api/query?"
            f"search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending&max_results={MAX_ITEMS_PER_ARXIV}"
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

            today = datetime.utcnow()
            items = []
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                link = entry.find("atom:id", ns)
                published = entry.find("atom:published", ns)
                authors = entry.findall("atom:author", ns)
                arxiv_comment = entry.find("arxiv:comment", ns)

                title_text = title.text.strip().replace("\n", " ") if title is not None else ""
                summary_text = summary.text.strip()[:500] if summary is not None else ""
                link_text = link.text.strip() if link is not None else ""
                published_text = published.text.strip() if published is not None else ""
                comment_text = arxiv_comment.text.strip() if arxiv_comment is not None else ""
                author_list = [a.find("atom:name", ns).text for a in authors if a.find("atom:name", ns) is not None]

                if not title_text or not link_text:
                    continue

                # LAMDA成员 + NJU精确匹配
                all_text = title_text + " " + summary_text + " " + " ".join(author_list) + " " + comment_text
                is_nju = check_nju(all_text, author_list)

                # arXiv链接转换
                arxiv_id = link_text.split("/abs/")[-1] if "/abs/" in link_text else ""
                html_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else link_text

                items.append(self.make_item(
                    url=html_url,
                    title=title_text,
                    summary=summary_text,
                    source_name=f"arXiv ({cat})",
                    source_type="api",
                    category="academic",
                    published=published_text,
                    is_nju=is_nju,
                    authors=author_list,
                    arxiv_id=arxiv_id,
                    comment=comment_text,
                ))

            return items

        except Exception as e:
            return []
