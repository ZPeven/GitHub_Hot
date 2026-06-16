"""Test translation with [TX]/[SX] prefix format"""
import sys, asyncio, aiohttp, re
sys.path.insert(0, "..")
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, PROXIES

async def test():
    items = [
        {"title": "APPO: Agentic Procedural Policy Optimization", "summary": "We present APPO, a novel framework for procedural policy optimization in autonomous agents. The method combines reinforcement learning with structured procedural knowledge.", "is_github": False},
        {"title": "LaWAM: Latent World Action Models", "summary": "We introduce LaWAM, a latent world action model for efficient robot policy learning. Our approach learns compact latent representations of environment dynamics.", "is_github": False},
    ]

    texts = []
    for i, item in enumerate(items):
        texts.append((i, "title", item["title"]))
        texts.append((i, "summary", item["summary"]))

    lines = []
    for idx, typ, text in texts:
        prefix = "T" if typ == "title" else "S"
        lines.append(f"[{prefix}{idx}] {text}")

    text_block = "\n".join(lines)
    print("=== Sending ===")
    print(text_block)
    print()

    system_prompt = (
        "You are a professional translator. "
        "Translate ALL following text into Simplified Chinese. "
        "Rules: Keep technical terms untranslated. Keep [TX]/[SX] prefix. Output ONLY translated lines."
    )

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Translate to Chinese:\n\n{text_block}"},
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions", headers=headers, json=payload,
            proxy=PROXIES["http"] if PROXIES else None,
        ) as resp:
            data = await resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""

    print("=== content ===")
    print(repr(content))
    print()
    print("=== reasoning_content ===")
    print(reasoning[:500])
    print()

    # Try parsing from both
    for source, label in [(content, "content"), (reasoning, "reasoning")]:
        if not source:
            continue
        print(f"=== Parsing from {label} ===")
        for line in source.split("\n"):
            line = line.strip()
            m = re.match(r'\[([TS])(\d+)\]\s*(.+)', line)
            if m:
                print(f"  OK: [{m.group(1)}{m.group(2)}] {m.group(3)[:60]}")
            elif re.match(r'\[', line):
                print(f"  UNMATCHED: {line[:80]}")

asyncio.run(test())
