#!/usr/bin/env python3
"""Package Torus into an installable zip and a Kodi repository.

Produces, under repo/ (served straight from GitHub raw):
    repo/addons.xml, repo/addons.xml.md5
    repo/plugin.video.torus/plugin.video.torus-<version>.zip
    repo/repository.torus/repository.torus-<REPO_VERSION>.zip

Run `python3 package.py` after bumping the addon version, then commit repo/.
Users who installed the repository addon get the new version automatically.
"""
import hashlib
import os
import shutil
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDON = "plugin.video.torus"
REPO = "repository.torus"
REPO_VERSION = "1.0.3"
GH_USER = "fanatic75"
# Published via GitHub Pages (main branch /docs), served at the site root — a
# short source URL like POV's kodifitzwell.github.io/repo/.
PUBLISH_DIR = "docs"
# Human-facing source URL (short) — used to add the source and install the repo zip.
SOURCE_URL = f"https://{GH_USER}.github.io/Torus/"
# The repository fetches UPDATES from raw.githubusercontent: github.io's CDN
# behaviour makes Kodi's checksum read fail, while raw works reliably (it's what
# other working repos use). Same files, different host.
DATADIR = f"https://raw.githubusercontent.com/{GH_USER}/Torus/main/{PUBLISH_DIR}/"

# Dev-only paths that must never ship inside the addon zip.
EXCLUDE_DIRS = {".git", "repo", "docs", "build", "__pycache__", ".devprofile",
                ".claude", ".github"}
EXCLUDE_FILES = {"deploy.sh", "package.py", "dev.config.json",
                 "dev.config.example.json", ".DS_Store"}

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Torus — TorBox Kodi Addon | native TorBox player for Kodi 21</title>
<meta name="description" content="Torus is a free, native TorBox Kodi addon: browse movies &amp; TV, play instantly-cached TorBox sources in Kodi, and resume where you left off. No API key — link TorBox with a device code. Kodi 21 / CoreELEC.">
<meta name="keywords" content="torbox kodi addon, torbox kodi, torbox addon, kodi torbox, torbox for kodi, torbox debrid kodi, kodi debrid addon, torbox stremio kodi, install torbox kodi">
<meta name="author" content="Prateek Banga">
<link rel="canonical" href="__SOURCE_URL__">

<!-- Open Graph / Twitter: renders a rich card when the link is shared on Reddit, forums, Discord, X. -->
<meta property="og:type" content="website">
<meta property="og:site_name" content="Torus">
<meta property="og:title" content="Torus — the TorBox Kodi addon">
<meta property="og:description" content="A free, native TorBox addon for Kodi. Browse movies &amp; TV, play instantly-cached TorBox sources, resume where you left off. No API key to type.">
<meta property="og:url" content="__SOURCE_URL__">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Torus — the TorBox Kodi addon">
<meta name="twitter:description" content="A free, native TorBox addon for Kodi. Play instantly-cached TorBox sources and resume where you left off. No API key to type.">

<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#127909;</text></svg>">

<!-- Structured data: helps Google show a rich result and helps LLMs (ChatGPT/Claude/Perplexity) parse what Torus is. -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Torus",
  "alternateName": "TorBox Kodi Addon",
  "applicationCategory": "MultimediaApplication",
  "operatingSystem": "Kodi 21 (Omega), CoreELEC, LibreELEC, Android, Windows, Linux, macOS",
  "description": "Torus is a native TorBox addon for Kodi. Browse movies and TV with keyless metadata, find instantly-playable TorBox-cached sources via Comet and Torrentio, play in Kodi's native player, and resume where you left off. No API key to type — TorBox is linked with a device code.",
  "url": "__SOURCE_URL__",
  "downloadUrl": "__SOURCE_URL____REPO_ZIP__",
  "softwareVersion": "__VERSION__",
  "license": "https://opensource.org/licenses/MIT",
  "author": { "@type": "Person", "name": "Prateek Banga" },
  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" }
}
</script>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Is there a TorBox addon for Kodi?",
      "acceptedAnswer": { "@type": "Answer", "text": "Yes. Torus is a free, open-source TorBox Kodi addon. You browse movies and TV inside Kodi, and Torus finds instantly-playable TorBox-cached sources and plays them in Kodi's native player." }
    },
    {
      "@type": "Question",
      "name": "How do I install TorBox on Kodi?",
      "acceptedAnswer": { "@type": "Answer", "text": "Enable Unknown sources in Kodi, add __SOURCE_URL__ as a file-manager source named Torus, install the repository zip from it, then install Torus from the Torus Repository. Open Torus and link your TorBox account with the device code." }
    },
    {
      "@type": "Question",
      "name": "Does the Torus TorBox addon need a TorBox API key?",
      "acceptedAnswer": { "@type": "Answer", "text": "No API key typing. Torus links your TorBox account with a phone-approved device code, so there is nothing to enter on a TV remote. You do need a paid TorBox account." }
    },
    {
      "@type": "Question",
      "name": "What Kodi versions does the TorBox addon support?",
      "acceptedAnswer": { "@type": "Answer", "text": "Torus targets Kodi 21 (Omega) and is developed and tested on CoreELEC. It runs on any Kodi 21 platform." }
    },
    {
      "@type": "Question",
      "name": "Is Torus free?",
      "acceptedAnswer": { "@type": "Answer", "text": "The Torus addon is free and open-source (MIT). It requires a paid TorBox account, which provides the cached sources it plays." }
    }
  ]
}
</script>
<style>
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; background:#0d1117; color:#e6edf3; line-height:1.6; }
.wrap { max-width:760px; margin:0 auto; padding:48px 20px 60px; }
header { text-align:center; margin-bottom:34px; }
h1 { font-size:2.6rem; margin:0 0 8px; letter-spacing:-.02em; background:linear-gradient(90deg,#7c9cff,#b98bff); -webkit-background-clip:text; background-clip:text; color:transparent; }
.tag { color:#9aa7b4; font-size:1.05rem; margin:0; }
.card { background:#161b22; border:1px solid #21262d; border-radius:14px; padding:22px 24px; margin:20px 0; }
h2 { font-size:1.15rem; margin:0 0 14px; }
.srcbox { display:flex; gap:10px; align-items:center; background:#0d1117; border:1px solid #30363d; border-radius:10px; padding:12px 14px; }
.srcbox code { font-size:1.05rem; color:#a5d6ff; word-break:break-all; flex:1; }
button.copy { background:#238636; color:#fff; border:0; border-radius:8px; padding:8px 14px; font-size:.9rem; cursor:pointer; white-space:nowrap; }
button.copy:hover { background:#2ea043; }
ol { padding-left:20px; margin:0; } li { margin:8px 0; }
.dl { display:inline-block; margin:10px 10px 0 0; background:#21262d; border:1px solid #30363d; color:#e6edf3; text-decoration:none; padding:10px 16px; border-radius:8px; font-size:.95rem; }
.dl:hover { border-color:#8b949e; }
.feat { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }
.feat div { background:#0d1117; border:1px solid #21262d; border-radius:10px; padding:12px 14px; font-size:.92rem; color:#c9d1d9; }
.faq h3 { font-size:1rem; margin:16px 0 4px; color:#e6edf3; }
.faq p { margin:0 0 4px; color:#c9d1d9; font-size:.95rem; }
footer { text-align:center; color:#6e7681; font-size:.85rem; margin-top:34px; }
a { color:#7c9cff; }
kbd { background:#21262d; border:1px solid #30363d; border-radius:5px; padding:1px 6px; font-size:.85em; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Torus</h1>
  <p class="tag">The <b>TorBox Kodi addon</b> — a native TorBox media browser for Kodi. Stremio-like, keyless, with local resume.</p>
</header>

<div class="card">
  <h2>Add this source in Kodi</h2>
  <div class="srcbox">
    <code id="src">__SOURCE_URL__</code>
    <button class="copy" onclick="navigator.clipboard.writeText(document.getElementById('src').textContent);this.textContent='Copied'">Copy</button>
  </div>
</div>

<div class="card">
  <h2>Install the TorBox addon on Kodi (auto-updates)</h2>
  <ol>
    <li>Enable <kbd>Settings &#8594; System &#8594; Add-ons &#8594; Unknown sources</kbd>.</li>
    <li><kbd>Settings &#8594; File manager &#8594; Add source</kbd> &#8594; paste the URL above &#8594; name it <b>Torus</b>.</li>
    <li><kbd>Add-ons &#8594; Install from zip file &#8594; Torus &#8594; repository.torus</kbd> &#8594; the repository zip.</li>
    <li><kbd>Add-ons &#8594; Install from repository &#8594; Torus Repository &#8594; Video add-ons &#8594; Torus &#8594; Install</kbd>.</li>
    <li>Open Torus &#8594; <b>&#128279; Link your TorBox account</b> &#8594; approve the code at <b>tor.box/link</b>.</li>
  </ol>
  <div>
    <a class="dl" href="__REPO_ZIP__">&#11015; repository zip</a>
    <a class="dl" href="__ADDON_ZIP__">&#11015; addon zip (v__VERSION__)</a>
  </div>
</div>

<!-- Folder links so Kodi's file browser can navigate this source (hidden from humans). -->
<div style="display:none">
  <a href="repository.torus/">repository.torus/</a>
  <a href="plugin.video.torus/">plugin.video.torus/</a>
</div>

<div class="card">
  <h2>What the TorBox Kodi addon does</h2>
  <div class="feat">
    <div>Keyless discovery (Cinemeta)</div>
    <div>TorBox device login &mdash; no typing</div>
    <div>Comet + Torrentio, merged</div>
    <div>TRaSH-tiered source ranking</div>
    <div>Resume &amp; Continue Watching</div>
    <div>TV Up Next</div>
    <div>Local Watchlist</div>
    <div>Works behind ISP DNS blocks</div>
  </div>
</div>

<div class="card faq">
  <h2>TorBox on Kodi — FAQ</h2>

  <h3>Is there a TorBox addon for Kodi?</h3>
  <p>Yes. <b>Torus</b> is a free, open-source TorBox Kodi addon. You browse movies and TV inside Kodi, and Torus finds instantly-playable TorBox-cached sources and plays them in Kodi's native player.</p>

  <h3>How do I install TorBox on Kodi?</h3>
  <p>Add <code>__SOURCE_URL__</code> as a file-manager source, install the repository zip, then install Torus from the Torus Repository (steps above). Link your TorBox account with the device code and you're done.</p>

  <h3>Does it need a TorBox API key?</h3>
  <p>No key typing. Torus links your TorBox account with a phone-approved device code — nothing to enter on a TV remote. You do need a <b>paid TorBox account</b>.</p>

  <h3>What Kodi versions are supported?</h3>
  <p>Kodi <b>21 (Omega)</b>, developed and tested on CoreELEC. It runs on any Kodi 21 platform.</p>

  <h3>Is Torus free?</h3>
  <p>Yes — the addon is free and open-source (MIT). It relies on your paid TorBox account for the cached sources it plays.</p>
</div>

<footer>
  Torus v__VERSION__ &middot; the TorBox Kodi addon &middot; <a href="__GH__">source on GitHub</a><br>
  Requires a TorBox account. Hosts no content, ships no indexers.
</footer>
</div>
</body>
</html>
"""


def addon_version() -> str:
    return ET.parse(os.path.join(ROOT, "addon.xml")).getroot().get("version")


def stage_addon() -> str:
    """Copy the addon files into build/plugin.video.torus/ (excluding dev files)."""
    dst_parent = os.path.join(ROOT, "build")
    dst = os.path.join(dst_parent, ADDON)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for name in files:
            if name in EXCLUDE_FILES:
                continue
            src = os.path.join(base, name)
            rel = os.path.relpath(src, ROOT)
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(src, out)
    return dst_parent


def write_repository_addon(build_parent: str) -> None:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<addon id="{REPO}" name="Torus Repository" version="{REPO_VERSION}" provider-name="Prateek Banga">
    <extension point="xbmc.addon.repository" name="Torus Repository">
        <dir>
            <info compressed="false">{DATADIR}addons.xml</info>
            <checksum>{DATADIR}addons.xml.md5</checksum>
            <datadir zip="true">{DATADIR}</datadir>
        </dir>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary lang="en_GB">Install and auto-update Torus</summary>
        <description lang="en_GB">Repository for the Torus addon.</description>
        <platform>all</platform>
    </extension>
</addon>
"""
    path = os.path.join(build_parent, REPO, "addon.xml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(xml)


def zip_addon(build_parent: str, addon_id: str, version: str) -> None:
    out_dir = os.path.join(ROOT, PUBLISH_DIR, addon_id)
    os.makedirs(out_dir, exist_ok=True)
    out_zip = os.path.join(out_dir, f"{addon_id}-{version}.zip")
    base = os.path.join(build_parent, addon_id)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for b, _, files in os.walk(base):
            for f in files:
                fp = os.path.join(b, f)
                arc = os.path.join(addon_id, os.path.relpath(fp, base))
                zf.write(fp, arc)
    # Keep only the current version's zip — a repo just needs the version that's
    # in addons.xml; stale zips are dead weight (that's how 0.7.0–0.7.3 piled up).
    keep = os.path.basename(out_zip)
    for f in os.listdir(out_dir):
        if f.endswith(".zip") and f != keep:
            os.remove(os.path.join(out_dir, f))
    print(f"  wrote {os.path.relpath(out_zip, ROOT)}")


def addon_xml_element(path: str) -> str:
    root = ET.parse(path).getroot()  # ET drops comments; root is <addon>
    return ET.tostring(root, encoding="unicode").strip()


def write_addons_xml(build_parent: str) -> None:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<addons>"]
    parts.append(addon_xml_element(os.path.join(build_parent, ADDON, "addon.xml")))
    parts.append(addon_xml_element(os.path.join(build_parent, REPO, "addon.xml")))
    parts.append("</addons>\n")
    xml = "\n".join(parts)
    repo_dir = os.path.join(ROOT, PUBLISH_DIR)
    os.makedirs(repo_dir, exist_ok=True)
    with open(os.path.join(repo_dir, "addons.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)
    md5 = hashlib.md5(xml.encode("utf-8")).hexdigest()
    # Trailing newline is required — Kodi's checksum reader fails on a bare hash.
    with open(os.path.join(repo_dir, "addons.xml.md5"), "w", encoding="utf-8") as fh:
        fh.write(md5 + "\n")
    print(f"  wrote docs/addons.xml (md5 {md5})")


def write_dir_indexes(version: str) -> None:
    """Directory listing pages so Kodi can browse into each folder (GitHub Pages
    doesn't auto-index directories)."""
    for folder, zip_name in ((ADDON, f"{ADDON}-{version}.zip"),
                             (REPO, f"{REPO}-{REPO_VERSION}.zip")):
        path = os.path.join(ROOT, PUBLISH_DIR, folder, "index.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f'<!doctype html><html><body>\n'
                     f'<a href="{zip_name}">{zip_name}</a>\n'
                     f'</body></html>\n')
    print("  wrote directory index pages")


def write_index_html(version: str) -> None:
    html = (INDEX_TEMPLATE
            .replace("__SOURCE_URL__", SOURCE_URL)
            .replace("__ADDON_ZIP__", f"plugin.video.torus/plugin.video.torus-{version}.zip")
            .replace("__REPO_ZIP__", f"repository.torus/repository.torus-{REPO_VERSION}.zip")
            .replace("__GH__", f"https://github.com/{GH_USER}/Torus")
            .replace("__VERSION__", version))
    with open(os.path.join(ROOT, PUBLISH_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("  wrote docs/index.html")


def main() -> None:
    version = addon_version()
    print(f"Packaging {ADDON} {version} + {REPO} {REPO_VERSION}")
    build_parent = stage_addon()
    write_repository_addon(build_parent)
    zip_addon(build_parent, ADDON, version)
    zip_addon(build_parent, REPO, REPO_VERSION)
    write_addons_xml(build_parent)
    write_index_html(version)
    write_dir_indexes(version)
    shutil.rmtree(os.path.join(build_parent))
    print("Done. Commit the docs/ folder to publish.")


if __name__ == "__main__":
    main()
