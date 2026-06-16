"""
智能去重处理器 — 标题相似度 + 内容指纹 + URL规范化
"""

from database import Database, make_fingerprint
from processors.nlp_utils import ChineseNLP


class Deduplicator:
    """多策略去重"""

    def __init__(self, db: Database):
        self.db = db
        self.recent_fingerprints = db.get_recent_fingerprints(days=7)
        self.seen_urls = set()

    def deduplicate(self, items: list[dict]) -> list[dict]:
        """
        多策略去重：
        1. URL完全匹配
        2. 内容指纹匹配
        3. 标题相似度 > 0.75
        """
        result = []
        for item in items:
            url = item.get("url", "")
            title = item.get("title", "")
            summary = item.get("summary", "")

            # 策略1: URL去重
            normalized = self.db.normalize_url(url)
            if normalized in self.seen_urls:
                continue

            # 策略2: 数据库指纹去重
            fp = make_fingerprint(title, summary)
            if fp in self.recent_fingerprints:
                continue

            # 策略3: 标题相似度去重（与已保留条目比较）
            is_dup = False
            for existing in result:
                sim = ChineseNLP.text_similarity(title, existing.get("title", ""))
                if sim > 0.72:
                    # 相似度太高，保留更完整的
                    if len(summary) > len(existing.get("summary", "")):
                        existing.update(item)
                    is_dup = True
                    break

            if is_dup:
                continue

            # 通过所有检查
            item["fingerprint"] = fp
            self.seen_urls.add(normalized)
            self.recent_fingerprints.add(fp)
            result.append(item)

        return result
