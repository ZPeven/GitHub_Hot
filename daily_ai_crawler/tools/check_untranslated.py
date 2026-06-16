"""Check which items lack translations"""
import sqlite3, sys
sys.path.insert(0, "..")
from processors.translator import Translator

db = sqlite3.connect("../crawler.db")
db.row_factory = sqlite3.Row
rows = db.execute("SELECT title, title_zh, summary_zh, source_name FROM history ORDER BY relevance_score DESC").fetchall()

untranslated = 0
total = 0
for r in rows:
    d = dict(r)
    title = d["title"]
    zh = d.get("title_zh") or ""
    szh = d.get("summary_zh") or ""

    should_t = Translator._should_translate_title(d)
    should_s = Translator._should_translate_summary(d)

    if should_t and not zh:
        untranslated += 1
        print(f"  MISS TITLE: [{d['source_name'][:20]}] {title[:60]}")
    if should_s and not szh:
        untranslated += 1
        print(f"  MISS SUMM:  [{d['source_name'][:20]}] {title[:40]}")
    total += 1

print(f"\nUntranslated: {untranslated}, Total checked: {total}")
db.close()
