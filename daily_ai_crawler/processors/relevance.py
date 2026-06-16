"""
相关性评分器 — 综合评估条目的AI相关度
"""

import re
from datetime import datetime, timedelta
from config import DOMAIN_KEYWORDS, SOURCE_AUTHORITY, MIN_RELEVANCE_SCORE
from processors.nlp_utils import ChineseNLP


class RelevanceScorer:
    """多维度相关性评分"""

    def __init__(self):
        self._all_kw = set()
        for domain, info in DOMAIN_KEYWORDS.items():
            for kw in info.get("zh", []):
                self._all_kw.add(kw.lower())
            for kw in info.get("en", []):
                self._all_kw.add(kw.lower())

    def score(self, item: dict) -> float:
        """
        评分维度：
        1. 关键词命中密度 (0-5)
        2. 来源权威度 (0-1)
        3. 内容长度质量 (-0.5 ~ 0.5)
        4. 标题质量 (-0.5 ~ 0.5)
        """
        score = 0.0
        title = item.get("title", "")
        summary = item.get("summary", "")
        text = (title + " " + summary).lower()

        # 1. 关键词命中 (-)
        kw_count = 0
        for kw in self._all_kw:
            if kw in text:
                kw_count += 1
        kw_density = min(kw_count / max(len(ChineseNLP.segment(text)), 1) * 100, 10)
        score += min(kw_density * 0.5, 5.0)

        # 2. 来源权威度 (支持前缀和子串匹配)
        source = item.get("source_name", "unknown").lower()
        authority = 0.3  # 默认
        for key, val in SOURCE_AUTHORITY.items():
            if key in source or source.startswith(key):
                authority = val
                break
        # source_type加分
        src_type = item.get("source_type", "")
        type_bonus = {"api": 0.1, "rss": 0.05, "web": 0.0, "search": -0.1}.get(src_type, 0)
        score += authority + type_bonus

        # 3. 内容长度质量
        content_len = len(text)
        if content_len > 200:
            score += 0.3
        elif content_len < 30:
            score -= 0.3

        # 4. 标题质量
        title_len = len(title)
        if title_len < 8:
            score -= 0.5
        elif title_len > 15:
            score += 0.2

        # 5. 中文内容加分（说明是国内相关）
        if ChineseNLP.has_chinese(title + summary):
            score += 0.1

        # 6. NJU专项加分
        if item.get("is_nju"):
            score += 1.5

        # 7. GitHub项目加分
        if item.get("is_github"):
            score += 0.5

        return round(score, 2)

    def filter(self, items: list[dict]) -> list[dict]:
        """评分并过滤低相关条目"""
        scored = []
        for item in items:
            s = self.score(item)
            item["relevance_score"] = s
            if s >= MIN_RELEVANCE_SCORE:
                scored.append(item)
        # 按评分降序排列
        scored.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return scored
