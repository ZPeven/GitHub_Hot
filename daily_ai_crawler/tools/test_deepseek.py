"""Test DeepSeek API connectivity"""
import sys, asyncio, aiohttp, json
sys.path.insert(0, "..")
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, PROXIES

async def test():
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "Translate tech titles concisely."},
            {"role": "user", "content": "Translate to English:\n[0] 三连发！阿里发布首个具身大模型Qwen-Robot系列"},
        ],
        "temperature": 0.3,
        "max_tokens": 256,
    }

    print(f"URL: {url}")
    print(f"Model: {DEEPSEEK_MODEL}")
    print(f"Key: sk-...{DEEPSEEK_API_KEY[-4:]}" if DEEPSEEK_API_KEY else "Key: NOT SET")

    # Test 1: direct (no proxy)
    print("\n--- Test 1: Direct (no proxy) ---")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                print(f"Status: {resp.status}")
                text = await resp.text()
                print(f"Body: {text[:300]}")
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: with proxy
    if PROXIES:
        print("\n--- Test 2: With proxy ---")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, proxy=PROXIES["http"], timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    print(f"Status: {resp.status}")
                    text = await resp.text()
                    print(f"Body: {text[:300]}")
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(test())
