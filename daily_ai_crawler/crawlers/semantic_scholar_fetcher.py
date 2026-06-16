"""
Semantic Scholar Academic Graph API 抓取器 (免费免申请)
— 精确按机构/作者过滤论文，替代 arXiv 粗粒度字符串匹配
"""

import asyncio
import urllib.parse
from crawlers.base import BaseCrawler
from config import (
    SEMANTIC_SCHOLAR_URL, MAX_ITEMS_SEMANTIC_SCHOLAR, DOMAIN_KEYWORDS,
)
from processors.lamda_matcher import check_nju


class SemanticScholarFetcher(BaseCrawler):
    """Semantic Scholar API — 免费版 (100次/5分钟)"""

    # 搜索字段：title,abstract,authors,year,venue,citationCount,externalIds,publicationTypes
    PAPER_FIELDS = "title,abstract,authors,year,venue,citationCount,externalIds,url,publicationDate,fieldsOfStudy"

    async def crawl(self) -> list[dict]:
        """并行搜索：AI热门方向 + 南大专项"""
        results = []

        # 按AI主题搜索 + 南大专项搜索
        search_tasks = [
            self._search("large language model agent 2025 2026", "Semantic Scholar: LLM+Agent", 6),
            self._search("reinforcement learning deep RL", "Semantic Scholar: RL", 4),
            self._search("spiking neural network neuromorphic", "Semantic Scholar: SNN", 3),
            self._search("world model embodied AI video generation", "Semantic Scholar: LWM", 3),
            self._search_nju(),
        ]

        task_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        for r in task_results:
            if isinstance(r, list):
                results.extend(r)

        return results

    async def _search(self, query: str, label: str, limit: int) -> list[dict]:
        """通用搜索"""
        try:
            encoded = urllib.parse.quote(query)
            url = (
                f"{SEMANTIC_SCHOLAR_URL}/paper/search?"
                f"query={encoded}&limit={limit}"
                f"&fields={self.PAPER_FIELDS}"
                f"&fieldsOfStudy=Computer Science"
                f"&sort=publicationDate:desc"
            )

            data = await self.fetch_json(url)
            if not data or "data" not in data:
                return []

            items = []
            for paper in data["data"]:
                title = paper.get("title", "")
                paper_url = paper.get("url", "")
                abstract = (paper.get("abstract") or "")[:400]
                year = paper.get("year", "")
                venue = paper.get("venue", "")
                citation_count = paper.get("citationCount", 0)
                authors = [a.get("name", "") for a in paper.get("authors", [])]
                fields = paper.get("fieldsOfStudy", [])

                if not title or not paper_url:
                    continue

                # LAMDA成员 + NJU精确匹配
                is_nju = check_nju(
                    f"{title} {abstract} {venue}",
                    authors,
                )

                # 来源标注
                venue_str = f" [{venue}]" if venue else ""
                cite_str = f" 📎{citation_count}" if citation_count else ""

                items.append(self.make_item(
                    url=paper_url,
                    title=title,
                    summary=f"{year}{venue_str} — {abstract}{cite_str}"[:500],
                    source_name=label,
                    source_type="api",
                    category="academic",
                    is_nju=is_nju,
                    authors=authors,
                    year=year,
                    venue=venue,
                    citation_count=citation_count,
                    fields=fields,
                ))

            return items

        except Exception:
            return []

    async def _search_nju(self) -> list[dict]:
        """南大论文专项搜索 — Semantic Scholar 核心优势：可按机构搜"""
        items = []

        # 合并搜索策略（减少API调用，免费版100次/5分钟）
        nju_queries = [
            "Nanjing University machine learning large language model agent",
            "NJU LAMDA deep learning computer science",
        ]

        tasks = [self._search(q, "Semantic Scholar: NJU", 8) for q in nju_queries]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        seen = set()
        for r in task_results:
            if isinstance(r, list):
                for item in r:
                    url = item.get("url", "")
                    if url and url not in seen:
                        seen.add(url)
                        item["is_nju"] = True
                        item["source_name"] = "Semantic Scholar: NJU"
                        items.append(item)

        return items
