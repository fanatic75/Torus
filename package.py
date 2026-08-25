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
GH_BRANCH = "main"
DATADIR = f"https://raw.githubusercontent.com/{GH_USER}/Torus/{GH_BRANCH}/repo/"

# Dev-only paths that must never ship inside the addon zip.
EXCLUDE_DIRS = {".git", "repo", "build", "__pycache__", ".devprofile", ".claude", ".github"}
EXCLUDE_FILES = {"deploy.sh", "package.py", "dev.config.json",
                 "dev.config.example.json", ".DS_Store"}


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
    out_dir = os.path.join(ROOT, "repo", addon_id)
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
    repo_dir = os.path.join(ROOT, "repo")
    os.makedirs(repo_dir, exist_ok=True)
    with open(os.path.join(repo_dir, "addons.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)
    md5 = hashlib.md5(xml.encode("utf-8")).hexdigest()
    with open(os.path.join(repo_dir, "addons.xml.md5"), "w", encoding="utf-8") as fh:
        fh.write(md5)
    print(f"  wrote repo/addons.xml (md5 {md5})")


def main() -> None:
    version = addon_version()
    print(f"Packaging {ADDON} {version} + {REPO} {REPO_VERSION}")
    build_parent = stage_addon()
    write_repository_addon(build_parent)
    zip_addon(build_parent, ADDON, version)
    zip_addon(build_parent, REPO, REPO_VERSION)
    write_addons_xml(build_parent)
    shutil.rmtree(os.path.join(build_parent))
    print("Done. Commit the repo/ folder to publish.")


if __name__ == "__main__":
    main()
