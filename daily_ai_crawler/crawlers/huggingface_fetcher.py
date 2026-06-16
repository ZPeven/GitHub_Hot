"""
HuggingFace Daily Papers 抓取器 (免费免申请)
— 社区投票选出的每日热门 ML 论文，直接反映业界关注热点
"""

import datetime
from crawlers.base import BaseCrawler
from config import HF_DAILY_PAPERS_URL, MAX_ITEMS_HF_PAPERS
from processors.lamda_matcher import check_nju


class HuggingFaceFetcher(BaseCrawler):
    """HuggingFace Daily Papers — 免费公开 API"""

    async def crawl(self) -> list[dict]:
        """抓取当日及近期热门论文"""
        results = []

        # 抓取当天
        today_items = await self._fetch_daily()
        results.extend(today_items)

        # 抓取前一天（避免当天还没更新）
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        yesterday_items = await self._fetch_daily(yesterday)
        results.extend(yesterday_items)

        return results

    async def _fetch_daily(self, date_str: str = None) -> list[dict]:
        """抓取指定日期的热门论文"""
        try:
            if date_str:
                url = f"{HF_DAILY_PAPERS_URL}?date={date_str}"
                label = f"HF Daily Papers ({date_str})"
            else:
                url = HF_DAILY_PAPERS_URL
                label = "HF Daily Papers"

            data = await self.fetch_json(url)
            if not data:
                return []

            items = []
            for paper in data[:MAX_ITEMS_HF_PAPERS]:
                # HF API 返回的字段
                paper_info = paper.get("paper", paper)  # 兼容嵌套结构
                title = paper_info.get("title", "")
                paper_id = paper_info.get("id", "")
                paper_url = f"https://huggingface.co/papers/{paper_id}" if paper_id else paper_info.get("url", "")
                abstract = (paper_info.get("abstract") or paper_info.get("summary", "") or "")[:400]

                # 上游赞数
                upvotes = paper.get("upvotes", paper.get("numUpvotes", 0))

                # 作者
                authors_raw = paper_info.get("authors", [])
                if isinstance(authors_raw, list):
                    authors = [a.get("name", a) if isinstance(a, dict) else str(a) for a in authors_raw]
                else:
                    authors = []

                if not title:
                    continue

                # arXiv 链接
                arxiv_id = paper_info.get("arxivId", "")
                if arxiv_id and not paper_url:
                    paper_url = f"https://arxiv.org/abs/{arxiv_id}"

                # LAMDA成员 + NJU精确匹配
                all_text = f"{title} {abstract} {' '.join(authors)}"
                is_nju = check_nju(all_text, authors)

                items.append(self.make_item(
                    url=paper_url,
                    title=title,
                    summary=f"👍{upvotes} — {abstract}"[:500],
                    source_name=label,
                    source_type="api",
                    category="academic",
                    is_nju=is_nju,
                    authors=authors,
                    upvotes=upvotes,
                    arxiv_id=arxiv_id,
                ))

            return items

        except Exception:
            return []
