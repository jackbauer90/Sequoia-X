"""Deployment adapter: wrap freshly generated original HTML, not a stale snapshot.

Not installed on the server yet. The existing dashboard generator can call
render_editorial(original_html) after producing its original HTML.
"""
import json
from pathlib import Path


def render_editorial(original_html: str) -> str:
    template = Path(__file__).with_name('editorial-shell.html').read_text(encoding='utf-8')
    # Escaping '<' prevents any source content from closing the JSON script tag.
    payload = json.dumps(original_html, ensure_ascii=False).replace('<', '\\u003c')
    marker = '<script id="sequoia-snapshot" type="application/json">' + payload + '</script>'
    return template.replace('</head>', '<meta http-equiv="refresh" content="60">' + marker + '</head>', 1)
