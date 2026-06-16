"""
DeepSeek API 翻译器 — 非中文标题+摘要统一翻译为中文
仅跳过: GitHub项目名、owner/repo、URL、已有中文的标题和摘要
"""

import asyncio
import re
import aiohttp
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    TRANSLATION_CONCURRENCY, REQUEST_TIMEOUT, PROXIES,
)


class Translator:
    """DeepSeek API 翻译器 — 非中文→中文，标题+摘要"""

    CHAT_URL = f"{DEEPSEEK_BASE_URL}/chat/completions"

    def __init__(self, session: aiohttp.ClientSession = None):
        self.session = session
        self._own_session = False
        self._semaphore = asyncio.Semaphore(TRANSLATION_CONCURRENCY)

    async def _ensure_session(self):
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=90)  # 日文+长文本需更长时间
            self.session = aiohttp.ClientSession(timeout=timeout)
            self._own_session = True

    async def close(self):
        if self._own_session and self.session:
            await self.session.close()

    @property
    def enabled(self) -> bool:
        return bool(DEEPSEEK_API_KEY)

    @staticmethod
    def _has_chinese(text: str) -> bool:
        """检测是否为中文（排除日文假名干扰）"""
        has_cjk = bool(re.search(r'[一-鿿]', text))
        if not has_cjk:
            return False
        # 如果包含日文假名，不是纯中文 → 需要翻译
        if re.search(r'[぀-ゟ゠-ヿ]', text):
            return False
        return True

    @staticmethod
    def _should_translate_title(item: dict) -> bool:
        """标题需要翻译的条件"""
        title = item.get("title", "")
        # 纯中文 → 不译
        if Translator._has_chinese(title):
            return False
        # GitHub 项目名 → 不译
        if item.get("is_github"):
            return False
        # owner/repo 格式 → 不译
        if re.match(r'^[\w.-]+\s*/\s*[\w.-]+$', title.strip()):
            return False
        # 太短 → 不译
        if len(title) < 6:
            return False
        return True

    @staticmethod
    def _should_translate_summary(item: dict) -> bool:
        """摘要需要翻译的条件（GitHub描述也要翻译）"""
        summary = item.get("summary", "")
        if not summary or len(summary) < 15:
            return False
        # 纯中文 → 不译
        if Translator._has_chinese(summary):
            return False
        return True

    # ── 批量翻译 ──────────────────────────────

    async def translate_all(self, items: list[dict]) -> list[dict]:
        if not self.enabled:
            return items

        await self._ensure_session()

        # 收集所有需翻译的文本 (标题 + 摘要)
        texts: list[tuple[int, str, str]] = []  # (item_idx, type, text)
        for i, item in enumerate(items):
            if self._should_translate_title(item):
                texts.append((i, "title", item["title"]))
            if self._should_translate_summary(item):
                texts.append((i, "summary", item["summary"]))

        if not texts:
            return items

        # 分批（每批最多10条文本，避免日文+长文本超时）
        batch_size = 10
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]

        tasks = [self._translate_batch(items, batch) for batch in batches]
        await asyncio.gather(*tasks, return_exceptions=True)

        return items

    async def _translate_batch(self, items: list[dict], texts: list[tuple[int, str, str]]):
        async with self._semaphore:
            try:
                # 构建翻译文本
                lines = []
                for idx, typ, text in texts:
                    prefix = "T" if typ == "title" else "S"
                    lines.append(f"[{prefix}{idx}] {text}")

                text_block = "\n".join(lines)

                system_prompt = (
                    "You are a professional translator. "
                    "Translate ALL following text into Simplified Chinese (简体中文). "
                    "Rules:\n"
                    "- Keep technical terms (LLM, RAG, RLHF, API, GPU, Python, etc.) in original form\n"
                    "- Keep proper nouns (company names, model names, person names) untranslated\n"
                    "- Keep the [TX] / [SX] prefix on each line\n"
                    "- Output ONLY the translated lines, no explanations, no extra text"
                )

                user_message = f"Translate to Chinese:\n\n{text_block}"

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

                    if not content or len(content) < 10:
                        reasoning = msg.get("reasoning_content", "")
                        if reasoning:
                            rlines = reasoning.strip().split("\n")
                            out = [l for l in reversed(rlines) if re.match(r'\[[TS]\d+\]', l.strip())]
                            content = "\n".join(reversed(out))

                    # 解析
                    for line in content.split("\n"):
                        line = line.strip()
                        m = re.match(r'\[([TS])(\d+)\]\s*(.+)', line)
                        if m:
                            prefix = m.group(1)
                            idx = int(m.group(2))
                            zh_text = m.group(3).strip().strip('"\'').strip()
                            if zh_text and idx < len(items):
                                orig = items[idx].get("title" if prefix == "T" else "summary", "")
                                if zh_text != orig:
                                    key = "title_zh" if prefix == "T" else "summary_zh"
                                    items[idx][key] = zh_text

            except Exception:
                pass
