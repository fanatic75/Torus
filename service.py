"""Torus background service — the resume engine.

Runs for the whole Kodi session. When Torus starts playback it stashes the media
identity (imdb/season/episode) in a window property; this service reads it, then
periodically and on pause/stop persists the play position to SQLite (keyed by
IMDb id, never the torrent). That's what powers Resume and Continue Watching.
"""
import json

import xbmc
import xbmcgui

from resources.lib import cinemeta, config, db

PLAYING_PROP = "torus.playing"
HOME = 10000  # Kodi Home window; properties here persist for the session.


class TorusPlayer(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.identity = None
        self.name = ""
        self.poster = ""

    def _read_identity(self):
        raw = xbmcgui.Window(HOME).getProperty(PLAYING_PROP)
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def onAVStarted(self):
        self.identity = self._read_identity()
        self.name, self.poster = "", ""
        if self.identity:
            # Fetch title/poster once so Continue Watching renders without extra calls.
            try:
                meta = cinemeta.meta(self.identity["mtype"], self.identity["imdb"])
                self.name = meta.get("name", "")
                self.poster = cinemeta.image(meta.get("poster"))
            except Exception as exc:  # noqa: BLE001 - metadata is best-effort
                xbmc.log(f"[Torus] resume meta lookup failed: {exc}", xbmc.LOGDEBUG)

    def save(self):
        if not self.identity:
            return
        try:
            position = self.getTime()
            duration = self.getTotalTime()
        except Exception:
            return
        if duration <= 0:
            return
        i = self.identity
        if position / duration > 0.9:  # effectively finished -> drop from Continue Watching
            db.clear_progress(i["imdb"], i.get("season", 0), i.get("episode", 0))
        else:
            db.save_progress(i["imdb"], i["mtype"], i.get("season", 0),
                             i.get("episode", 0), position, duration,
                             self.name, self.poster, i.get("url", ""))

    def onPlayBackPaused(self):
        self.save()

    def onPlayBackStopped(self):
        self.save()
        self.identity = None

    def onPlayBackEnded(self):
        if self.identity:
            db.clear_progress(self.identity["imdb"],
                              self.identity.get("season", 0),
                              self.identity.get("episode", 0))
        self.identity = None


def main() -> None:
    monitor = xbmc.Monitor()
    player = TorusPlayer()
    xbmc.log("[Torus] service started", xbmc.LOGINFO)

    # Prune only if the user enabled it; otherwise keep everything (Continue
    # Watching just shows the 40 most recent). Runs at startup + ~daily.
    def maybe_prune():
        if not config.prune_enabled():
            return
        try:
            removed = db.prune(config.prune_days())
            if removed:
                xbmc.log(f"[Torus] pruned {removed} old resume points", xbmc.LOGINFO)
        except Exception as exc:  # noqa: BLE001
            xbmc.log(f"[Torus] prune failed: {exc}", xbmc.LOGDEBUG)

    day_seconds = 24 * 60 * 60
    elapsed = 0
    maybe_prune()

    while not monitor.abortRequested():
        if player.isPlaying() and player.identity:
            player.save()
        elapsed += 15
        if elapsed >= day_seconds:
            elapsed = 0
            maybe_prune()
        if monitor.waitForAbort(15):
            break

    xbmc.log("[Torus] service stopped", xbmc.LOGINFO)


if __name__ == "__main__":
    main()
