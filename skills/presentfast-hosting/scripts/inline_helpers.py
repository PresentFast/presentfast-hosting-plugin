"""
Reusable helpers for making an HTML file self-contained for PresentFast hosting.

PresentFast renders a deck inside an about:srcdoc iframe under a strict CSP that blocks
external <script>/<link>. These helpers inline those dependencies so the deck works.

Import from a build script:
    from inline_helpers import (
        inline_external_tag, data_uri, download, embed_sibling_srcdoc, assert_no_external
    )

All functions are pure string transforms except download(). They assert() when an expected
marker is missing, so a source change fails loudly instead of silently skipping an inline.
"""
import base64
import subprocess
import urllib.request


def download(url: str) -> str:
    """Fetch a text asset (e.g. a specific pinned library version) to inline."""
    with urllib.request.urlopen(url) as r:
        return r.read().decode("utf-8")


def inline_external_tag(html: str, exact_tag: str, inner: str, kind: str) -> str:
    """
    Replace an exact external <script src>/<link rel=stylesheet> tag with an inline block.

    exact_tag : the full tag string as it appears in the source (copy it verbatim).
    inner     : the downloaded JS or CSS text to inline.
    kind      : "script" or "style".

    We match the exact tag (not a regex) so a version bump or attribute change surfaces as a
    failed assert rather than a wrong/duplicate replacement.
    """
    assert exact_tag in html, f"expected tag not found (source changed?): {exact_tag[:80]!r}"
    if kind == "script":
        block = f"<script>/* inlined for CSP */\n{inner}\n</script>"
    elif kind == "style":
        block = f"<style>/* inlined for CSP */\n{inner}\n</style>"
    else:
        raise ValueError("kind must be 'script' or 'style'")
    return html.replace(exact_tag, block)


def drop_tag(html: str, exact_tag: str, note: str = "removed for CSP") -> str:
    """Remove a blocked tag entirely (e.g. a Google Fonts <link> when relying on font fallback)."""
    assert exact_tag in html, f"tag to drop not found: {exact_tag[:80]!r}"
    return html.replace(exact_tag, f"<!-- {note} -->")


def compress_image(src_path: str, out_path: str, max_dim: int = 1000, quality: int = 60) -> str:
    """
    Downscale + JPEG-compress an image. Returns out_path.

    Uses whichever tool is available: macOS `sips`, or ImageMagick `magick`/`convert`
    (Linux/Windows/anywhere). Raises if none is installed.
    """
    import shutil
    if shutil.which("sips"):
        subprocess.run(
            ["sips", "-Z", str(max_dim), "-s", "format", "jpeg",
             "-s", "formatOptions", str(quality), src_path, "--out", out_path],
            check=True, capture_output=True,
        )
        return out_path
    # ImageMagick: both v7 `magick` and v6 `convert` accept `in -resize ... -quality ... out`.
    tool = shutil.which("magick") or shutil.which("convert")
    if tool:
        subprocess.run(
            [tool, src_path, "-resize", f"{max_dim}x{max_dim}>", "-quality", str(quality), out_path],
            check=True, capture_output=True,
        )
        return out_path
    raise RuntimeError("Need `sips` (macOS) or ImageMagick (`magick`/`convert`) to compress images.")


def data_uri(path: str, mime: str = "image/jpeg") -> str:
    """Return a base64 data: URI for a binary asset (image, font, ...)."""
    b = open(path, "rb").read()
    return f"data:{mime};base64," + base64.b64encode(b).decode("ascii")


def inline_image(html: str, src_value: str, path: str, mime: str = "image/jpeg") -> str:
    """Replace src="<src_value>" with a data: URI for the file at `path`."""
    needle = f'src="{src_value}"'
    assert needle in html, f"image ref not found: {needle!r}"
    return html.replace(needle, f'src="{data_uri(path, mime)}"')


# ---- Embedding a sibling HTML file into a parent via iframe.srcdoc ----
#
# Why base64 + runtime decode instead of writing the sibling HTML straight into a JS string:
# the sibling contains its own </script> tags, which would terminate the parent's inline
# <script> early and corrupt the page. Base64 has no '<', so it embeds safely; we decode it
# UTF-8-safe at runtime (the sibling has em dashes, ³, etc.).

_DECODER_JS = """(function(b64){
  var bin = atob(b64);
  var bytes = new Uint8Array(bin.length);
  for (var i=0;i<bin.length;i++) bytes[i]=bin.charCodeAt(i);
  return new TextDecoder('utf-8').decode(bytes);
})"""


def embed_sibling_srcdoc(
    parent_html: str,
    self_contained_sibling_html: str,
    *,
    global_name: str = "__EMBED_HTML",
    old_src_line: str,
    new_src_line: str,
) -> str:
    """
    Embed a (already self-contained) sibling deck into the parent so it loads via iframe.srcdoc.

    - Injects `window.<global_name> = <decoded sibling html>` just before </body>.
    - Rewrites the parent's iframe-loading line from an `.src =` assignment to a `.srcdoc =` one.

    old_src_line : the exact line in the parent that currently sets the iframe source, e.g.
                   'if(!ifr.src && ifr.dataset.src) ifr.src = ifr.dataset.src;'
    new_src_line : its replacement, e.g.
                   'if(!ifr.srcdoc && window.__EMBED_HTML){ ifr.srcdoc = window.__EMBED_HTML; }'

    The parent keeps same-origin access to the child (postMessage / contentWindow), which is
    required if the parent drives the embedded app.
    """
    b64 = base64.b64encode(self_contained_sibling_html.encode("utf-8")).decode("ascii")
    inject = f'<script>\nwindow.{global_name} = {_DECODER_JS}("{b64}");\n</script>\n'

    assert old_src_line in parent_html, f"iframe src line not found: {old_src_line!r}"
    parent_html = parent_html.replace(old_src_line, new_src_line)

    assert "</body>" in parent_html, "no </body> to inject before"
    return parent_html.replace("</body>", inject + "</body>", 1)


def assert_no_external(html: str, hosts=("cdnjs.cloudflare.com", "unpkg.com",
                                         "fonts.googleapis.com", "fonts.gstatic.com",
                                         "jsdelivr.net")) -> None:
    """Fail the build if any known-blocked external host still appears in a src/href."""
    import re
    for host in hosts:
        for m in re.finditer(r'(src|href)="https?://[^"]*' + re.escape(host), html):
            raise AssertionError(f"external reference to blocked host remains: {host} ({m.group(0)[:80]})")
