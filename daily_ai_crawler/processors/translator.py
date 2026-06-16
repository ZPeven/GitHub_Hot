"""
DeepSeek API 中英双语翻译器
— 仅翻译新闻标题，不翻译论文标题/项目名/URL
"""

import asyncio
import json
import re
import aiohttp
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    TRANSLATION_CONCURRENCY, REQUEST_TIMEOUT, PROXIES,
)


class Translator:
    """DeepSeek API 翻译器 — 仅翻译新闻标题（论文标题和项目名保持原文）"""

    CHAT_URL = f"{DEEPSEEK_BASE_URL}/chat/completions"

    def __init__(self, session: aiohttp.ClientSession = None):
        self.session = session
        self._own_session = False
        self._semaphore = asyncio.Semaphore(TRANSLATION_CONCURRENCY)

    async def _ensure_session(self):
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)
            self._own_session = True

    async def close(self):
        if self._own_session and self.session:
            await self.session.close()

    @property
    def enabled(self) -> bool:
        return bool(DEEPSEEK_API_KEY)

    # ── 语言检测 ──────────────────────────────

    @staticmethod
    def _has_chinese(text: str) -> bool:
        return bool(re.search(r'[一-鿿]', text))

    @staticmethod
    def _should_translate(item: dict) -> bool:
        """
        判断标题是否需要翻译：
        - 跳过学术论文标题（arxiv来源）
        - 跳过 GitHub 项目名
        - 跳过太短的标题（< 6字符）
        - 已在学术源的不翻译
        """
        source_type = item.get("source_type", "")
        source_name = item.get("source_name", "")
        title = item.get("title", "")

        # 不翻译论文标题
        if source_type == "api" and ("arxiv" in source_name.lower() or
                                       "semantic scholar" in source_name.lower() or
                                       "hf daily" in source_name.lower()):
            return False

        # 不翻译 GitHub 项目名
        if item.get("is_github"):
            return False

        # 不翻译太短的标题
        if len(title) < 8:
            return False

        return True

    # ── 批量翻译 ──────────────────────────────

    async def translate_all(self, items: list[dict]) -> list[dict]:
        """批量翻译所有需要翻译的标题（并发控制）"""
        if not self.enabled:
            return items

        await self._ensure_session()

        # 过滤需要翻译的条目
        to_translate = [it for it in items if self._should_translate(it)]
        if not to_translate:
            return items

        # 分批处理（每批最多20个标题，避免单次请求过大）
        batch_size = 20
        batches = [to_translate[i:i + batch_size] for i in range(0, len(to_translate), batch_size)]

        tasks = [self._translate_batch(batch) for batch in batches]
        await asyncio.gather(*tasks, return_exceptions=True)

        return items

    async def _translate_batch(self, items: list[dict]):
        """翻译一批标题"""
        async with self._semaphore:
            try:
                # 构建翻译prompt
                titles = []
                for i, item in enumerate(items):
                    titles.append(f"[{i}] {item['title']}")

                titles_text = "\n".join(titles)

                # 检测大部分标题的语言来决定翻译方向
                cn_count = sum(1 for it in items if self._has_chinese(it["title"]))
                en_count = len(items) - cn_count

                if cn_count >= en_count:
                    # 中文标题 → 翻译成英文
                    direction = "将以下中文标题翻译成英文，只返回翻译结果，保持编号格式"
                else:
                    # 英文标题 → 翻译成中文
                    direction = "Translate the following English titles into Chinese. Only return translations, keep the number format"

                system_prompt = (
                    "You are a professional translator for AI/tech news headlines. "
                    "Translate accurately and concisely. "
                    "Keep technical terms in their original form (LLM, RAG, RLHF, etc.). "
                    "Do NOT add explanations, notes, or extra text. "
                    "Output ONLY the translated titles, one per line, keeping the [N] prefix."
                )

                user_message = f"{direction}:\n\n{titles_text}"

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                }

                payload = {
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4096,
                }

                async with self.session.post(
                    self.CHAT_URL,
                    headers=headers,
                    json=payload,
                    proxy=PROXIES["http"] if PROXIES else None,
                ) as resp:
                    if resp.status != 200:
                        return

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"].strip()

                    # 解析翻译结果
                    translations = {}
                    for line in content.split("\n"):
                        line = line.strip()
                        match = re.match(r'\[(\d+)\]\s*(.+)', line)
                        if match:
                            idx = int(match.group(1))
                            text = match.group(2).strip()
                            translations[idx] = text

                    # 赋值到对应条目
                    for i, item in enumerate(items):
                        if i in translations:
                            translated = translations[i]
                            # 清理多余的引号和标记
                            translated = translated.strip('"\'').strip()
                            if translated and translated != item["title"]:
                                item["title_en"] = translated

            except Exception:
                # 翻译失败不阻塞主流程
                pass
