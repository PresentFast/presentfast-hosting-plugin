#!/usr/bin/env python3
"""
Generic build template — copy next to inline_helpers.py, edit the CONFIG block, run.

Turns a static HTML file (and optionally a sibling it embeds) into CSP-safe self-contained
*.dist.html for PresentFast, then tells you the publish command.

Two paths below:
  • SINGLE FILE  — the common case (one page, some CDN libs, some images).
  • MULTI-FILE   — a parent page that embeds a sibling .html via an <iframe> (optional; delete if unused).

Nothing here is app-specific: fill in your own tags, filenames, and library URLs.
"""
import base64, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
from inline_helpers import (
    download, inline_external_tag, drop_tag, compress_image, inline_image,
    embed_sibling_srcdoc, assert_no_external,
)

# ============================ CONFIG — edit this ============================
SRC = "/path/to/source_dir"      # where your .html + images live
OUT = "/tmp/pf_build"            # where *.dist.html get written
os.makedirs(OUT, exist_ok=True)

MAIN_HTML = "index.html"         # the page you want to host

# External <script src>/<link> tags to inline. Copy each EXACTLY as it appears in the source
# (whitespace, attribute order, trailing slash all matter — the helper asserts an exact match).
# Map each tag -> (kind, url_to_download). kind is "script" or "style".
EXTERNAL_TAGS = {
    # '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>':
    #     ("script", "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"),
    # '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />':
    #     ("style",  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"),
}

# Blocked <link> tags to simply remove (typically Google Fonts — the CSS font-family fallback covers it).
DROP_TAGS = [
    # '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">',
]

# Local images -> how to compress. src_value is the exact src="..." in the HTML.
# (src_value, source_png_path, max_dim, quality)
IMAGES = [
    # ("hero.png",      f"{SRC}/hero.png",      1000, 60),
    # ("chart-bg.png",  f"{SRC}/chart-bg.png",  1200, 70),
]

# --- MULTI-FILE only (leave SIBLING_HTML = None for a single-file deck) ---
SIBLING_HTML = None              # e.g. "panel.html" — a local page the main page embeds in an <iframe>
# The exact line in MAIN_HTML that currently points the iframe at the sibling, and its srcdoc replacement.
# Find it with:  grep -n "\.src *=" index.html   (often inside a lazy-loader, e.g. `ifr.src = ifr.dataset.src`)
EMBED_OLD_LINE = "ifr.src = ifr.dataset.src;"
EMBED_NEW_LINE = "if(!ifr.srcdoc && window.__EMBED_HTML){ ifr.srcdoc = window.__EMBED_HTML; }"
EMBED_GLOBAL   = "__EMBED_HTML"
# ===========================================================================


def make_self_contained(html: str) -> str:
    """Inline every configured external dependency (shared by main + sibling)."""
    for tag in DROP_TAGS:
        html = drop_tag(html, tag)
    for tag, (kind, url) in EXTERNAL_TAGS.items():
        html = inline_external_tag(html, tag, download(url), kind)
    return html


# 1) If there's a sibling, make IT self-contained first (so it can be base64'd into the parent).
sibling_sc = None
if SIBLING_HTML:
    sibling_sc = make_self_contained(open(f"{SRC}/{SIBLING_HTML}", encoding="utf-8").read())
    open(f"{OUT}/{SIBLING_HTML.replace('.html', '.dist.html')}", "w", encoding="utf-8").write(sibling_sc)

# 2) Main page: inline deps, inline images, (optionally) embed the sibling via srcdoc.
main = make_self_contained(open(f"{SRC}/{MAIN_HTML}", encoding="utf-8").read())

for src_value, png, max_dim, q in IMAGES:
    jpg = f"{OUT}/" + re.sub(r"[^A-Za-z0-9]+", "_", src_value) + ".jpg"
    compress_image(png, jpg, max_dim=max_dim, quality=q)
    main = inline_image(main, src_value, jpg)

if SIBLING_HTML:
    main = embed_sibling_srcdoc(
        main, sibling_sc,
        global_name=EMBED_GLOBAL,
        old_src_line=EMBED_OLD_LINE,
        new_src_line=EMBED_NEW_LINE,
    )

out_main = f"{OUT}/{MAIN_HTML.replace('.html', '.dist.html')}"
open(out_main, "w", encoding="utf-8").write(main)

# 3) Validate.
assert_no_external(main)
if sibling_sc:
    assert_no_external(sibling_sc)
    blob = re.search(r'\}\)\("([A-Za-z0-9+/=]+)"\);', main)
    assert blob and base64.b64decode(blob.group(1)).decode("utf-8") == sibling_sc, "embedded sibling mismatch"

print("OK ->", out_main, f"({os.path.getsize(out_main):,} bytes)")
print("Publish:  npx -y @presentfast/cli@latest publish", out_main, '--title "..."')
