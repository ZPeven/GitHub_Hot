"""
DeepSeek API 翻译器 — 非中文内容统一翻译为中文
仅跳过: 项目名、owner/repo、URL、已有中文的标题
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
    """DeepSeek API 翻译器 — 非中文→中文，单向批量翻译"""

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

    # ── 过滤 ──────────────────────────────────

    @staticmethod
    def _has_chinese(text: str) -> bool:
        return bool(re.search(r'[一-鿿]', text))

    @staticmethod
    def _should_translate(item: dict) -> bool:
        """仅跳过：项目名、owner/repo格式、URL、已有中文的"""
        title = item.get("title", "")

        # 已有中文 → 不翻译
        if Translator._has_chinese(title):
            return False

        # GitHub 项目名
        if item.get("is_github"):
            return False

        # owner/repo 格式 (如 "PaddlePaddle/Paddle" 或 "owner / repo")
        if re.match(r'^[\w.-]+\s*/\s*[\w.-]+$', title.strip()):
            return False

        # 太短
        if len(title) < 8:
            return False

        return True

    # ── 批量翻译 ──────────────────────────────

    async def translate_all(self, items: list[dict]) -> list[dict]:
        """批量翻译所有非中文标题 → 中文"""
        if not self.enabled:
            return items

        await self._ensure_session()

        to_translate = [it for it in items if self._should_translate(it)]
        if not to_translate:
            return items

        # 分批（每批最多20条）
        batch_size = 20
        batches = [to_translate[i:i + batch_size] for i in range(0, len(to_translate), batch_size)]

        tasks = [self._translate_batch(batch, i) for i, batch in enumerate(batches)]
        await asyncio.gather(*tasks, return_exceptions=True)

        return items

    async def _translate_batch(self, items: list[dict], batch_idx: int):
        """翻译一批非中文标题 → 中文"""
        async with self._semaphore:
            try:
                titles = []
                for i, item in enumerate(items):
                    titles.append(f"[{i}] {item['title']}")

                titles_text = "\n".join(titles)

                system_prompt = (
                    "You are a professional translator. "
                    "Translate the following titles into Simplified Chinese (简体中文). "
                    "Rules:\n"
                    "- Keep technical terms untranslated (LLM, RAG, RLHF, API, GPU, etc.)\n"
                    "- Keep proper nouns (company names, model names, person names) in original form\n"
                    "- Keep the [N] prefix for each line\n"
                    "- Output ONLY translated lines, no explanations"
                )

                user_message = f"Translate these titles to Chinese:\n\n{titles_text}"

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
                    "max_tokens": 8192,
                }

                async with self.session.post(
                    self.CHAT_URL, headers=headers, json=payload,
                    proxy=PROXIES["http"] if PROXIES else None,
                ) as resp:
                    if resp.status != 200:
                        return

                    data = await resp.json()
                    msg = data["choices"][0]["message"]
                    content = (msg.get("content") or msg.get("reasoning_content") or "").strip()

                    # 从reasoning_content中提取翻译结果（如果content为空）
                    if not content or len(content) < 10:
                        reasoning = msg.get("reasoning_content", "")
                        if reasoning:
                            lines = reasoning.strip().split("\n")
                            translated_lines = []
                            for line in reversed(lines):
                                line = line.strip()
                                if re.match(r'\[(\d+)\]', line):
                                    translated_lines.insert(0, line)
                            if translated_lines:
                                content = "\n".join(translated_lines)

                    # 解析翻译结果
                    translations = {}
                    for line in content.split("\n"):
                        line = line.strip()
                        match = re.match(r'\[(\d+)\]\s*(.+)', line)
                        if match:
                            idx = int(match.group(1))
                            text = match.group(2).strip().strip('"\'').strip()
                            if text:
                                translations[idx] = text

                    # 赋值
                    for i, item in enumerate(items):
                        if i in translations:
                            zh = translations[i]
                            if zh and zh != item["title"]:
                                item["title_zh"] = zh

            except Exception:
                pass
