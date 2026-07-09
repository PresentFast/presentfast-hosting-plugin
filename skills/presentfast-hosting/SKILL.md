---
name: presentfast-hosting
description: >-
  Host, publish, upload, or share a static HTML file, dashboard, demo, slide deck, or landing page on
  presentfast.com (PresentFast). Use this WHENEVER the user wants an existing page on PresentFast — even
  casually ("throw this up on presentfast", "make sales-dashboard.html a presentfast link", "publish my deck to
  presentfast") — whether or not a file is named and even if they don't mention CSP or inlining. ALSO use it to
  fix a page already on PresentFast that renders wrong: blank
  map, missing/unstyled charts, wrong fonts, images or tiles not loading, or anything that works locally but
  breaks once live. This matters because PresentFast renders in a strict-CSP about:srcdoc iframe that blocks
  external scripts/stylesheets (cdnjs, Google Fonts), so naive publishing silently breaks maps, charts, fonts,
  and multi-file decks; the skill makes the page self-contained, embeds sibling HTML, publishes with the right
  tool, and verifies the live render. Not for hosting elsewhere (Vercel, Netlify, GitHub Pages, npm).
---

# Hosting static HTML on PresentFast

PresentFast publishes an HTML (or Markdown) file to `https://www.presentfast.com/docs/<slug>-<uuid>`.
It looks like a plain static host, but the rendering model has sharp edges that break most real-world
dashboards unless you prepare the file. This skill exists so you don't rediscover them the hard way.

## The one thing to internalize

**The deck runs inside an `about:srcdoc` iframe governed by the viewer's Content-Security-Policy.**
That CSP allows inline `<script>`/`<style>` but **forbids loading external scripts and stylesheets.**
So a dashboard that pulls Leaflet/Chart.js/D3 from a CDN, or fonts from Google Fonts, will publish
successfully and then render broken (blank map, unstyled, fallback fonts). Everything that must run has
to live *inside* the file. Images are the exception — remote `https:` images and `data:` URIs both work.

Read `references/csp-and-rendering.md` for the exact CSP, the full allow/block table, and why each rule
matters. Skim it before your first publish on a new deck; it will save you a broken upload.

## Workflow

1. **Inspect the source.** Find every external dependency and every local/relative reference:
   ```bash
   grep -oE '(src|href)="https?://[^"]*"' file.html | sort -u        # external scripts/styles/fonts
   grep -oE '(src|href)="[^"]*"' file.html | grep -viE 'https?://|="#' # local files (images, sibling html)
   grep -c '<script' file.html                                         # is it JS-driven? (usually yes)
   ```
   Note which CDN libraries load, which fonts, which images, and whether the page embeds a sibling
   `.html` (an `<iframe src="...">` or `data-src="..."`).

2. **Confirm the CSP** (optional but fast — it can change over time):
   ```bash
   # Publish a tiny probe first (see below), then:
   curl -sI "https://www.presentfast.com/docs/<probe-slug>" | grep -i content-security-policy
   ```

3. **Make the file self-contained.** Use `scripts/inline_helpers.py` — it has tested functions for each
   case. The rules:
   - **External `<script src>`** (Leaflet, Chart.js, …) → download that exact version, inline as `<script>…</script>`.
   - **External `<link rel=stylesheet>`** (library CSS) → download, inline as `<style>…</style>`.
   - **Google Fonts / web fonts** → usually just **delete the `<link>` and rely on the CSS fallback**
     (`'Inter', system-ui, sans-serif` degrades cleanly to the system font). Only inline `@font-face`
     with base64 `data:` woff2 if pixel-perfect fonts are essential — it's heavy, so default to fallback.
   - **Local images** → compress and inline as `data:` URIs (see step 4).
   - **Remote `https:` images / map tiles** → leave as-is; `img-src https:` allows them.
   - **Library icon assets** (e.g. Leaflet's default marker PNGs referenced by relative `url()` in its CSS)
     → these 404 under CSP. Check if the deck actually uses them; Leaflet `divIcon`/`circleMarker` need no
     assets, so many maps are fine. If default markers are used, inline the marker PNGs as data URIs.

4. **Compress images before inlining** — data URIs bloat the file ~33%, and PresentFast has upload limits.
   Downscale to the size the image actually displays and re-encode as JPEG:
   ```bash
   # macOS:
   sips -Z 1000 -s format jpeg -s formatOptions 60 big.png --out small.jpg
   # Linux / Windows (ImageMagick):
   magick big.png -resize 1000x -quality 60 small.jpg          # or: convert big.png ...
   ```
   Then embed as `data:image/jpeg;base64,…`. Match quality to how large it displays.
   (`scripts/inline_helpers.py::compress_image` auto-detects whichever tool is installed.)

5. **Embed sibling HTML via `iframe.srcdoc`, not a URL.** If the deck embeds another local `.html`
   (relative `src` — which 404s under CSP), inline it. **Base64-encode the sibling and set `iframe.srcdoc`
   at runtime** (raw string embedding breaks on the sibling's own `</script>` tags). This keeps parent and
   child **same-origin**, so the parent's `contentWindow`/`postMessage` control of the child still works —
   which pointing the iframe at a separately-published URL would break (the iframe's `contentWindow` would
   be PresentFast's wrapper page, not the child deck). First make the *sibling* self-contained (its own
   Leaflet/CSS inlined), then base64 that. See `references/csp-and-rendering.md` § "Multi-file decks" and
   the `embed_sibling_srcdoc` helper.

6. **Build deterministically with a script, don't hand-edit.** Write a small `build.py` that reads the
   source, asserts each expected external reference is present (so a source change fails loudly instead of
   silently skipping an inline), performs the replacements, and writes `*.dist.html`. `scripts/inline_helpers.py`
   is importable; **copy `scripts/build_template.py`, edit its CONFIG block** (your tags, images, and optional
   sibling), and run it — it covers both the single-file and the multi-file (embedded sibling) cases.

7. **Validate the build before uploading:**
   ```bash
   grep -c 'cdnjs\|unpkg\|fonts.googleapis' dist.html   # must be 0
   grep -c 'src="data:image' dist.html                  # images inlined
   ```
   For an embedded sibling, decode the base64 blob back and confirm it matches the self-contained sibling
   byte-for-byte (the example build does this).

8. **Publish with the right tool** (this matters — see below).

9. **Verify the live render** in a real browser (see "Verification"). Never claim it works from a successful
   upload alone — the CSP breakage only shows at render time.

## Publishing: CLI vs MCP tool

PresentFast is reachable two ways. Pick by file size:

- **`@presentfast/cli` — use for any real file, especially >100KB.** It reads the file server-side, so the
  upload is **byte-exact** and costs no model tokens:
  ```bash
  npx -y @presentfast/cli@latest publish dist.html --title "My Dashboard"
  npx -y @presentfast/cli@latest ls
  npx -y @presentfast/cli@latest delete <id> --yes      # MCP has no delete; the CLI does
  npx -y @presentfast/cli@latest login --device         # if not authenticated; token persists after
  ```
  `rename`, `links` (gated share links), and `analytics` also exist.
- **MCP `publish_presentation` tool** — only for small decks composed in the conversation. It takes the full
  HTML inline as a `content` argument, so routing a large existing file through it is expensive and can
  corrupt the bytes. Good for the tiny CSP/render **probe**, not for a 1MB dashboard.
  Related MCP tools: `update_presentation` (edit in place, keeps the URL + analytics), `get_presentation_content`,
  `list_presentations`, `get_presentation_analytics`, `create_share_link`.

**Probe pattern:** to test CSP or rendering behavior cheaply, publish a tiny HTML via the MCP tool, load it,
then `update_presentation` to iterate on the same URL. Keep one throwaway probe deck rather than spamming new ones.

## Verification (do not skip)

The deck renders client-side inside the srcdoc iframe, so `curl` only returns PresentFast's Next.js shell —
**you cannot verify with curl.** Use a real browser:

- **Headless Chrome screenshot (most reliable, no extension needed):**
  ```bash
  # CHROME = your Chrome/Chromium binary:
  #   macOS:   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  #   Linux:   google-chrome   (or chromium / chromium-browser)
  #   Windows: "C:\Program Files\Google\Chrome\Application\chrome.exe"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1440,900 \
    --virtual-time-budget=15000 --screenshot=/tmp/shot.png \
    "https://www.presentfast.com/docs/<slug>"
  ```
  `--virtual-time-budget` lets the SPA + inlined JS finish before capture. Then Read the PNG.
- **Chrome extension MCP** (`mcp__claude-in-chrome__*`) when you need to *click* through nav (e.g. reach an
  inner page or an embedded sub-deck). It can be flaky/disconnect; the headless path is a solid fallback.
- **Verify the risky, CSP-dependent features specifically** — the map actually drawing tiles, charts
  rendering, images visible, fonts acceptable. If a sub-feature lives behind in-app navigation you can't
  click headlessly, **publish that sub-deck standalone and screenshot it** — if the self-contained sibling
  renders under the real CSP, the srcdoc-embedded copy (byte-identical, same origin, same CSP) will too.
- Note: console output from the srcdoc iframe is **not** captured by top-page console tools, so rely on the
  visual/screenshot rather than console scraping.

## Gotchas checklist

- [ ] No external `<script src>` / `<link rel=stylesheet>` remain (grep returns 0).
- [ ] `location.hash` is always empty in srcdoc — don't rely on hash routing; drive inner state via JS/postMessage.
- [ ] Relative `src="sibling.html"` / `url(images/x.png)` never resolve — inline them.
- [ ] Sibling HTML embedded via base64 → `srcdoc` (not a URL), decoded UTF-8-safe with `TextDecoder`.
- [ ] Images compressed before base64; total file within reason.
- [ ] Published via CLI (large) not the MCP inline tool.
- [ ] Live render screenshotted under the real CSP, including the map/chart/image, not just the landing view.
