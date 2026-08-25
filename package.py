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
REPO_VERSION = "1.0.0"
GH_USER = "fanatic75"
# Published via GitHub Pages (main branch /docs), served at the site root — a
# short source URL like POV's kodifitzwell.github.io/repo/.
PUBLISH_DIR = "docs"
DATADIR = f"https://{GH_USER}.github.io/Torus/"

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
<title>Torus — Kodi addon</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#127909;</text></svg>">
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
footer { text-align:center; color:#6e7681; font-size:.85rem; margin-top:34px; }
a { color:#7c9cff; }
kbd { background:#21262d; border:1px solid #30363d; border-radius:5px; padding:1px 6px; font-size:.85em; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Torus</h1>
  <p class="tag">A TorBox-native media browser for Kodi — Stremio-like, keyless, with local resume.</p>
</header>

<div class="card">
  <h2>Add this source in Kodi</h2>
  <div class="srcbox">
    <code id="src">__SOURCE_URL__</code>
    <button class="copy" onclick="navigator.clipboard.writeText(document.getElementById('src').textContent);this.textContent='Copied'">Copy</button>
  </div>
</div>

<div class="card">
  <h2>Install (auto-updates)</h2>
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
  <h2>What it does</h2>
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

<footer>
  Torus v__VERSION__ &middot; <a href="__GH__">source on GitHub</a><br>
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
    with open(os.path.join(repo_dir, "addons.xml.md5"), "w", encoding="utf-8") as fh:
        fh.write(md5)
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
            .replace("__SOURCE_URL__", DATADIR)
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
