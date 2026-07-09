# presentfast-hosting

A Claude Code plugin that hosts static HTML files, dashboards, and demos on **[presentfast.com](https://www.presentfast.com)** *correctly*.

PresentFast renders every deck inside a strict-CSP `about:srcdoc` iframe that **blocks external scripts and stylesheets** (cdnjs, unpkg, Google Fonts). So publishing a real dashboard as-is silently breaks its maps, charts, and fonts. This plugin's skill makes the page fully self-contained (inlines libraries/CSS, images as `data:` URIs, and any embedded sibling HTML via `srcdoc`), publishes it with the right tool for the file size, and verifies the live render in a real browser.

## What's inside

- **Skill: `presentfast-hosting`** — the workflow (inspect → inline → build → publish → verify), a CSP reference, and reusable build helpers.

## Install

```bash
# Add this repo as a marketplace, then install the plugin:
/plugin marketplace add CHANGE-ME/presentfast-hosting-plugin
/plugin install presentfast-hosting@presentfast-hosting-plugin
```

Or, if it's listed in the community marketplace:

```bash
/plugin marketplace add anthropics/claude-plugins-community
/plugin install presentfast-hosting@claude-community
```

## Prerequisites

- **PresentFast account + CLI login** (separate from any MCP connector):
  ```bash
  npx -y @presentfast/cli@latest login --device
  ```
- **Image compression:** macOS `sips` (built in) or ImageMagick (`magick`/`convert`) on Linux/Windows — the build helper auto-detects.
- **Verification:** a local Chrome/Chromium for headless screenshots.

## Usage

Just ask Claude to host something on PresentFast, e.g. *"publish index.html to presentfast"* or *"my leaflet map is blank after I put it on presentfast — fix it."* The skill triggers automatically.

## License

MIT — see [LICENSE](LICENSE).
