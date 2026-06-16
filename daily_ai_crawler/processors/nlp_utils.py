"""
中文NLP工具 — 分词、关键词提取、文本相似度
"""

import re
import jieba
from collections import Counter


class ChineseNLP:
    """中文文本处理工具集"""

    # 停用词
    STOP_WORDS = set(
        "的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 "
        "会 着 没有 看 好 自己 这 他 她 它 们 那 些 什么 而 为 所以 因为 "
        "可以 不是 这个 那个 但是 如果 虽然 然而 然后 之后 以前 以后 现在 "
        "如何 怎么 怎样 能够 已经 正在 将 要 了 被 把 从 对 与 及 以及 "
        "或 并 但 且 其 让 用 还 等 之 中 与 更 最".split()
    )

    @classmethod
    def segment(cls, text: str) -> list[str]:
        """中文分词，过滤停用词和标点"""
        words = jieba.cut(text)
        return [
            w.strip() for w in words
            if len(w.strip()) > 1
            and w.strip() not in cls.STOP_WORDS
            and not re.match(r'^[^\w一-鿿]+$', w)
        ]

    @classmethod
    def extract_keywords(cls, text: str, top_n: int = 10) -> list[tuple[str, int]]:
        """提取关键词及其频次"""
        words = cls.segment(text)
        counter = Counter(words)
        return counter.most_common(top_n)

    @classmethod
    def text_similarity(cls, text1: str, text2: str) -> float:
        """基于词集合的 Jaccard 相似度"""
        words1 = set(cls.segment(text1))
        words2 = set(cls.segment(text2))
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    @classmethod
    def has_chinese(cls, text: str) -> bool:
        """检测是否包含中文"""
        return bool(re.search(r'[一-鿿]', text))

    @classmethod
    def clean_html(cls, text: str) -> str:
        """清理HTML标签"""
        clean = re.sub(r'<[^>]+>', ' ', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    @classmethod
    def normalize_title(cls, title: str) -> str:
        """标准化标题：去除多余空格、特殊字符"""
        title = re.sub(r'\s+', ' ', title)
        title = re.sub(r'[「」『』""'']', '"', title)
        title = re.sub(r'[【】\[\]]', '[', title)
        return title.strip()
