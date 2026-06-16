"""Test DeepSeek translation with real items"""
import sys, asyncio, aiohttp
sys.path.insert(0, "..")
from config import PROXIES
from processors.translator import Translator

async def test():
    # Simulate real items that need translation
    items = [
        {"title": "三连发！阿里发布首个具身大模型Qwen-Robot系列", "source_type": "rss", "source_name": "量子位"},
        {"title": "智源大会开幕，从悟道到悟界，智源研究院推动人工智能新突破", "source_type": "rss", "source_name": "雷锋网-AI"},
        {"title": "Anthropic宣告递归自我提升时代到来，LLM如何实现自我进化", "source_type": "rss", "source_name": "Bing News AI"},
        {"title": "14天速成LLM高手，大佬开源学习笔记", "source_type": "rss", "source_name": "Bing News LLM"},
        {"title": "4步出声，单卡0.24秒！Noiz AI联合港科大清华，开源音频生成大模型", "source_type": "rss", "source_name": "量子位"},
    ]

    translator = Translator()
    async with aiohttp.ClientSession() as session:
        translator.session = session
        result = await translator.translate_all(items)

    print("\n=== Translation Results ===")
    for item in result:
        orig = item["title"][:60]
        en = item.get("title_en", "NOT TRANSLATED")
        print(f"  ZH: {orig}")
        print(f"  EN: {en}")
        print()

asyncio.run(test())
