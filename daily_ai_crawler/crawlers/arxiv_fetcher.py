"""
arXiv API 论文抓取器
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from crawlers.base import BaseCrawler
from config import MAX_ITEMS_PER_ARXIV, NJU_KEYWORDS, DOMAIN_KEYWORDS


class ArxivFetcher(BaseCrawler):
    """arXiv 学术论文抓取 — 按分类 + 南大作者过滤"""

    async def crawl(self) -> list[dict]:
        """抓取 arXiv 最新论文"""
        categories = ["cs.AI", "cs.LG", "cs.CL", "cs.MA"]
        results = []
        for cat in categories:
            items = await self._fetch_category(cat)
            results.extend(items)
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

                # 南大作者检测
                is_nju = False
                all_text = title_text + " " + summary_text + " " + " ".join(author_list) + " " + comment_text
                for kw in NJU_KEYWORDS:
                    if kw.lower() in all_text.lower():
                        is_nju = True
                        break

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
