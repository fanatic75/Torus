"""Test bootstrap.

The addon modules import Kodi's `xbmc*` modules, which don't exist off-Kodi.
We install minimal stubs so everything imports under plain CPython. We deliberately
do NOT stub `xbmcaddon`/`xbmcvfs`, so `resources.lib.config` runs in its off-Kodi
"dev" mode (settings from dev.config.json/defaults) — which keeps config/db tests
deterministic and Kodi-free.

The `xbmcplugin`/`xbmcgui.Window` stubs RECORD what the addon does (directory
items added, resolved URLs, window properties) so router/handler tests can assert
on behaviour. The `kodi` fixture resets and exposes those records.
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


# --- recorded state (see the `kodi` fixture) -------------------------------
_DIR_ITEMS = []   # dicts: {handle, url, item, folder}
_RESOLVED = []    # dicts: {handle, ok, item}
_WIN = {}         # window properties (Window(id).setProperty/clearProperty)
_PLAYER = {"playing": False, "stopped": 0, "played": [], "played_items": []}  # xbmc.Player() state
_PL = {"items": [], "pos": -1}               # xbmc.PlayList(VIDEO): item paths + position


def _reset_records():
    _DIR_ITEMS.clear()
    _RESOLVED.clear()
    _WIN.clear()
    _PLAYER.update(playing=False, stopped=0)
    _PLAYER["played"] = []
    _PLAYER["played_items"] = []
    _PL["items"] = []
    _PL["pos"] = -1


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
    def contextmenu(self, *a, **k): return -1
    def input(self, *a, **k): return ""
    def yesno(self, *a, **k): return False
    def ok(self, *a, **k): pass


class _Window:
    """Backed by the shared _WIN dict so tests can inspect window properties."""
    def __init__(self, *a, **k): pass
    def getProperty(self, k): return _WIN.get(k, "")
    def setProperty(self, k, v): _WIN[k] = str(v)
    def clearProperty(self, k): _WIN.pop(k, None)


class _DialogProgress:
    def create(self, *a, **k): pass
    def update(self, *a, **k): pass
    def close(self): pass
    def iscanceled(self): return False


_xbmcgui.Dialog = _Dialog
_xbmcgui.Window = _Window
_xbmcgui.DialogProgress = _DialogProgress

# --- xbmcplugin (recording) ------------------------------------------------
_xbmcplugin = _stub("xbmcplugin")
_xbmcplugin.addDirectoryItem = lambda handle, url, item=None, isFolder=False, *a, **k: \
    _DIR_ITEMS.append({"handle": handle, "url": url, "item": item, "folder": isFolder})
_xbmcplugin.setResolvedUrl = lambda handle, ok, item, *a, **k: \
    _RESOLVED.append({"handle": handle, "ok": ok, "item": item})
_xbmcplugin.endOfDirectory = lambda *a, **k: None
_xbmcplugin.setContent = lambda *a, **k: None
_xbmcplugin.setPluginCategory = lambda *a, **k: None
_xbmcplugin.addSortMethod = lambda *a, **k: None


# --- xbmc.Player / xbmc.PlayList (recording) -------------------------------
class _Player:
    def __init__(self, *a, **k): pass
    def isPlaying(self): return _PLAYER["playing"]
    def isPlayingVideo(self): return _PLAYER["playing"]
    def stop(self): _PLAYER["stopped"] += 1
    def play(self, *a, **k):
        item = a[0] if a else None
        _PLAYER["played"].append(item)
        _PLAYER["played_items"].append(a[1] if len(a) > 1 else None)
        _PLAYER["playing"] = True
        # Playing a PlayList makes Kodi start at item 0 — model that so tests can
        # simulate autoplay-next advancing through PLAYLIST_VIDEO.
        if hasattr(item, "getposition"):
            _PL["pos"] = 0 if _PL["items"] else -1
    def getPlayingFile(self): return ""


class _PlayList:
    def __init__(self, *a, **k): pass
    def getposition(self): return _PL["pos"]
    def __len__(self): return len(_PL["items"])
    def __getitem__(self, i):
        li = _ListItem()
        li.setPath(_PL["items"][i])
        return li
    def add(self, url, listitem=None, index=None, *a, **k): _PL["items"].append(url)
    def remove(self, path): _PL["items"][:] = [p for p in _PL["items"] if p != path]
    def clear(self): _PL["items"].clear()


_xbmc.Player = _Player
_xbmc.PlayList = _PlayList


# --- fixtures --------------------------------------------------------------
@pytest.fixture
def tmp_profile(tmp_path, monkeypatch):
    """Point the addon's profile dir (where db + tokens live) at a temp dir."""
    from resources.lib import config
    monkeypatch.setattr(config, "profile_dir", lambda: str(tmp_path))
    monkeypatch.setattr(config, "_profile_dir", lambda: str(tmp_path))
    return tmp_path


@pytest.fixture
def kodi():
    """Reset and expose what the addon told Kodi: directory items, resolved URLs,
    and window properties."""
    _reset_records()

    class _View:
        items = _DIR_ITEMS
        resolved = _RESOLVED
        win = _WIN
        player = _PLAYER
        playlist = _PL
    return _View()
