"""
领域分类器 — 将条目分类到 AI 子领域
"""

from config import DOMAIN_KEYWORDS
from processors.nlp_utils import ChineseNLP


class Classifier:
    """AI子领域分类"""

    def __init__(self):
        # 扁平化关键词映射
        self._kw_map = {}  # keyword -> (domain, weight)
        for domain, info in DOMAIN_KEYWORDS.items():
            weight = info["weight"]
            for kw in info.get("zh", []):
                self._kw_map[kw.lower()] = (domain, weight)
            for kw in info.get("en", []):
                self._kw_map[kw.lower()] = (domain, weight)

    def classify(self, item: dict) -> str:
        """分类单条记录，返回主领域标签"""
        text = (item.get("title", "") + " " + item.get("summary", "")).lower()
        scores = {}

        for kw, (domain, weight) in self._kw_map.items():
            if kw in text:
                scores[domain] = scores.get(domain, 0) + weight

        if not scores:
            return "ml"  # 默认归入机器学习

        # 返回得分最高的领域
        return max(scores, key=scores.get)

    def classify_all(self, items: list[dict]) -> list[dict]:
        """批量分类"""
        for item in items:
            item["sub_category"] = self.classify(item)
        return items
