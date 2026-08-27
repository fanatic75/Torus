"""Test bootstrap.

The addon modules import Kodi's `xbmc*` modules, which don't exist off-Kodi.
We install minimal stubs so everything imports under plain CPython. We deliberately
do NOT stub `xbmcaddon`/`xbmcvfs`, so `resources.lib.config` runs in its off-Kodi
"dev" mode (settings from dev.config.json/defaults) — which keeps config/db tests
deterministic and Kodi-free.
"""
import sys
import types

import pytest


def _stub(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


# --- xbmc ------------------------------------------------------------------
_xbmc = _stub("xbmc")
_xbmc.LOGDEBUG, _xbmc.LOGINFO, _xbmc.LOGWARNING, _xbmc.LOGERROR = 0, 1, 2, 3
_xbmc.log = lambda *a, **k: None
_xbmc.executebuiltin = lambda *a, **k: None
_xbmc.sleep = lambda *a, **k: None
_xbmc.PLAYLIST_VIDEO = 1


class _InfoTag:
    """Records set*/returns get* — enough for listing/main to run."""
    def __init__(self):
        self._d = {}

    def __getattr__(self, name):
        if name.startswith("set"):
            key = name[3:]
            return lambda *a: self._d.__setitem__(key, a[0] if len(a) == 1 else a)
        if name.startswith("get"):
            key = name[3:]
            return lambda *a: self._d.get(key, "")
        raise AttributeError(name)


class _ListItem:
    def __init__(self, label="", label2="", path="", offscreen=False):
        self._label, self._path = label, path
        self._art, self._props, self._ctx = {}, {}, []
        self._tag = _InfoTag()

    def setLabel(self, s): self._label = s
    def getLabel(self): return self._label
    def setLabel2(self, s): pass
    def setPath(self, p): self._path = p
    def getPath(self): return self._path
    def setArt(self, d): self._art.update(d)
    def setProperty(self, k, v): self._props[k] = str(v)
    def getProperty(self, k): return self._props.get(k, "")
    def setInfo(self, *a, **k): pass
    def addContextMenuItems(self, items, *a): self._ctx = items
    def getVideoInfoTag(self): return self._tag


# --- xbmcgui ---------------------------------------------------------------
_xbmcgui = _stub("xbmcgui")
_xbmcgui.ListItem = _ListItem
_xbmcgui.NOTIFICATION_INFO, _xbmcgui.NOTIFICATION_WARNING, _xbmcgui.NOTIFICATION_ERROR = 0, 1, 2
_xbmcgui.INPUT_ALPHANUM = 0


class _Dialog:
    def notification(self, *a, **k): pass
    def select(self, *a, **k): return -1
    def input(self, *a, **k): return ""
    def yesno(self, *a, **k): return False
    def ok(self, *a, **k): pass


class _Window:
    def __init__(self, *a, **k): pass
    def getProperty(self, k): return ""
    def setProperty(self, k, v): pass


class _DialogProgress:
    def create(self, *a, **k): pass
    def update(self, *a, **k): pass
    def close(self): pass
    def iscanceled(self): return False


_xbmcgui.Dialog = _Dialog
_xbmcgui.Window = _Window
_xbmcgui.DialogProgress = _DialogProgress

# --- xbmcplugin ------------------------------------------------------------
_xbmcplugin = _stub("xbmcplugin")
for _fn in ("addDirectoryItem", "endOfDirectory", "setContent", "setResolvedUrl",
            "setPluginCategory", "addSortMethod"):
    setattr(_xbmcplugin, _fn, lambda *a, **k: None)


# --- fixtures --------------------------------------------------------------
@pytest.fixture
def tmp_profile(tmp_path, monkeypatch):
    """Point the addon's profile dir (where db + tokens live) at a temp dir."""
    from resources.lib import config
    monkeypatch.setattr(config, "profile_dir", lambda: str(tmp_path))
    monkeypatch.setattr(config, "_profile_dir", lambda: str(tmp_path))
    return tmp_path
