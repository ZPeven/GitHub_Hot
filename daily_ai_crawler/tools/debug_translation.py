"""Debug: check which items are being filtered for translation"""
import sys, sqlite3
sys.path.insert(0, "..")

db = sqlite3.connect("../crawler.db")
db.row_factory = sqlite3.Row
rows = db.execute(
    "SELECT title, source_name, source_type FROM history ORDER BY relevance_score DESC LIMIT 30"
).fetchall()

from processors.translator import Translator

yes_count = 0
no_count = 0
for r in rows:
    item = dict(r)
    ok = Translator._should_translate(item)
    src = item["source_name"][:25]
    if ok:
        yes_count += 1
        print(f"  [YES] {src:25s} | {item['title'][:60]}")
    else:
        no_count += 1

print(f"\nTranslatable: {yes_count}, Skipped: {no_count}")
print(f"Total: {len(rows)}")
db.close()
