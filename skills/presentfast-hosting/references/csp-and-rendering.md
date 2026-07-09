# PresentFast rendering model & CSP — the details

This is the "why" behind the skill. Read it once per new deck so the inlining choices are obvious.

## How a deck is served

- Publishing a file returns a URL: `https://www.presentfast.com/docs/<slug>-<uuid>`.
- That URL is a **Next.js single-page app**. `curl` of the URL returns the app shell (`Loading…`,
  `_next/static/...` chunks) — **not your HTML**. Your deck content is fetched client-side and injected
  into an **`about:srcdoc` iframe**, full-bleed. Consequence: you can only inspect the real render in a
  browser that runs JS, never with curl.
- Because it's `about:srcdoc`, the deck document **inherits the parent page's origin and CSP**, and its
  base URL is the `/docs/...` page — so relative URLs resolve against `/docs/` and 404.

## The CSP (observed; re-check with `curl -sI <deck-url> | grep -i content-security-policy`)

```
default-src 'self';
script-src  'self' 'unsafe-inline' 'unsafe-eval' https://va.vercel-scripts.com https://*.vercel-insights.com;
style-src   'self' 'unsafe-inline';
img-src     'self' data: blob: https:;
font-src    'self' data:;
connect-src 'self' https: wss:;
frame-ancestors 'self'; form-action 'self' ...; base-uri 'self'; object-src 'none';
upgrade-insecure-requests
```

### What that means for a deck

| Resource | Allowed? | So you must… |
|---|---|---|
| Inline `<script>…</script>` | ✅ (`'unsafe-inline'` + `'unsafe-eval'`) | keep app JS inline (it already is) |
| External `<script src="https://cdnjs…">` | ❌ blocked | **download & inline** the library |
| Inline `<style>` / `style=""` | ✅ (`'unsafe-inline'`) | keep CSS inline |
| External `<link rel=stylesheet href="cdnjs/Google Fonts">` | ❌ blocked | **inline** library CSS; drop font links |
| Web font files (gstatic woff2) | ❌ (only `'self' data:`) | rely on font fallback, or inline `@font-face` as `data:` |
| `<img src="data:…">` | ✅ | inline local images as data URIs |
| `<img src="https://…">` incl. map tiles | ✅ (`img-src … https:`) | leave remote images/tiles alone |
| `fetch()/XHR/WebSocket` to `https://`/`wss://` | ✅ | remote APIs still work |
| Relative `src="sibling.html"` / `url(images/x.png)` | ❌ 404 (resolves to `/docs/…`) | inline the sibling / asset |

### Fonts: prefer fallback

Well-built decks declare `font-family: 'Inter', system-ui, sans-serif` (and `monospace` for mono). When the
Google Fonts stylesheet is blocked, the browser uses `system-ui` — clean and near-identical on most machines.
So the default move is **delete the Google Fonts `<link>`** and accept the fallback. Only inline `@font-face`
with base64 woff2 (heavy: multiple weights × ~30–50KB) if the exact typeface is essential to the design.

### Library icon assets are a trap

Some libraries' CSS references images by relative `url()` — e.g. Leaflet's `url(images/marker-icon.png)`.
Under CSP+srcdoc those relative URLs 404. Check whether the deck actually uses them:
- Leaflet with `L.divIcon` (HTML markers) or `L.circleMarker` (SVG) → **no image assets, you're fine**.
- Leaflet with default `L.marker(...)` and no custom icon → needs `marker-icon.png`/`marker-shadow.png`;
  inline those as data URIs (set `L.Icon.Default.prototype.options` or `L.Icon.Default.imagePath`) or switch
  to divIcons.
Map **tiles** always load (they're `https:` images).

## Multi-file decks (parent embeds a sibling `.html`)

A parent that shows another local page in an `<iframe>` has two failure modes to avoid:

1. **Relative `src` 404s** — covered above.
2. **Pointing the iframe at a separately-published sibling URL breaks parent→child control.** PresentFast
   wraps *every* deck in its own srcdoc iframe. So if the parent's iframe `src` is the sibling's
   `/docs/...` URL, then `iframe.contentWindow` is PresentFast's **wrapper page**, and the sibling deck is a
   *further* nested srcdoc inside it. `postMessage`/`contentWindow` calls the parent makes to "the sibling
   app" never reach it.

**Fix: inline the sibling via `iframe.srcdoc`.** Steps:
1. Make the sibling itself self-contained (inline its own Leaflet/CSS/etc.).
2. **Base64-encode** the sibling HTML (raw-string embedding breaks on the sibling's `</script>` tags; base64
   contains no `<`).
3. At runtime set `iframe.srcdoc = decode(BASE64)`, decoding **UTF-8-safe** via `TextDecoder` (siblings have
   em dashes, `³`, etc. that `atob` alone mangles):
   ```js
   iframe.srcdoc = (function(b64){
     var bin = atob(b64), bytes = new Uint8Array(bin.length);
     for (var i=0;i<bin.length;i++) bytes[i]=bin.charCodeAt(i);
     return new TextDecoder('utf-8').decode(bytes);
   })(SIBLING_B64);
   ```
An `about:srcdoc` child is **same-origin** with the parent, so `postMessage` and `contentWindow` control work
exactly as they did on `file://` or a normal server. (Robust decks already talk to their embed over
`postMessage` with `'*'` — that keeps working.) `scripts/inline_helpers.py::embed_sibling_srcdoc` does this.

## Other srcdoc quirks

- **`location.hash` is always empty** in the deck. Anything that used `#hash` scene/routing won't fire —
  drive inner state by calling into the app (`iframe.contentWindow.someFn()` / `postMessage`) instead.
- **Console messages from the srcdoc iframe are not captured** by top-page console tooling — verify visually.
- Newly published decks are `noindex,nofollow` and the URL is unguessable (UUID). Treat the URL as the
  access control; use `create_share_link` (MCP) for password/email/domain gating if needed.

## Publishing tools recap

- **`@presentfast/cli`** reads the file server-side → byte-exact, token-free, no size-through-model problem.
  Use for anything real. `publish`, `ls`, `delete <id> --yes`, `rename`, `links`, `analytics`, `login --device`.
- **MCP `publish_presentation`** takes HTML inline as `content` → good only for tiny probes / conversation-
  composed decks. `update_presentation` edits in place and keeps the URL + analytics — handy for iterating a
  probe on one stable URL. The MCP surface has **no delete**; the CLI does.

## Verification recipe

```bash
# CHROME = your Chrome/Chromium binary — macOS: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
# Linux: google-chrome (or chromium); Windows: "C:\Program Files\Google\Chrome\Application\chrome.exe"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1440,900 \
  --virtual-time-budget=15000 --screenshot=/tmp/shot.png "https://www.presentfast.com/docs/<slug>"
```
Then look at `/tmp/shot.png`. Confirm the CSP-dependent parts specifically: map tiles drawn, markers present,
charts rendered, images visible, fonts acceptable. For a feature behind in-app nav you can't click headlessly,
screenshot the **standalone** sub-deck — identical bytes + same origin + same CSP means the embedded copy
renders the same.
