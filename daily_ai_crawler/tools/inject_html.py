"""Replace INDEX_HTML in app.py with new design from a separate HTML file"""
import sys, re

app_path = sys.argv[1] if len(sys.argv) > 1 else "../app.py"
html_path = sys.argv[2] if len(sys.argv) > 2 else None

with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# Find the INDEX_HTML block
start_marker = 'INDEX_HTML = r"""'
start = content.index(start_marker)
prefix = content[:start]

# Find closing </html>"""
end_match = re.search(r'\n</html>"""', content)
# Skip past the closing </html>""" (12 chars: \n + </html>""")
suffix = content[end_match.start() + len('\n</html>"""'):]

# Insert new HTML
if html_path:
    with open(html_path, "r", encoding="utf-8") as f:
        new_html = f.read()
else:
    # Read from stdin
    new_html = sys.stdin.read()

new_content = prefix + 'INDEX_HTML = r"""' + new_html + '\n</html>"""' + suffix

with open(app_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"Done. Injected {len(new_html)} chars of HTML into {app_path}")
