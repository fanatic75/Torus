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
        self.advanced = False    # have we already marked this item finished?
        self.last_ratio = 0.0    # last observed watched fraction (0 = never played)

    def _read_identity(self):
        raw = xbmcgui.Window(HOME).getProperty(PLAYING_PROP)
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def onPlayBackStarted(self):
        # Capture identity per attempt so a failed play can't act on a stale one.
        self.identity = self._read_identity()
        self.advanced = False
        self.last_ratio = 0.0

    def onPlayBackError(self):
        # Playback failed to open (expired link, no network, ...). Never touch
        # the resume point — just forget what we were trying to play.
        self.identity = None

    def onAVStarted(self):
        if not self.identity:
            self.identity = self._read_identity()
        self.name, self.poster = "", ""
        self.advanced = False
        self.last_ratio = 0.0
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
        self.last_ratio = position / duration
        if self.last_ratio > 0.9:  # effectively finished
            if not self.advanced:
                self._advance()
        else:
            i = self.identity
            db.save_progress(i["imdb"], i["mtype"], i.get("season", 0),
                             i.get("episode", 0), position, duration,
                             self.name, self.poster, i.get("url", ""))

    def _next_episode(self, identity):
        """Return the next episode after the current one, or None."""
        if not identity or identity.get("mtype") != "series":
            return None
        return cinemeta.next_episode(identity["imdb"], identity.get("season", 0),
                                     identity.get("episode", 0))

    def _advance(self):
        """Mark the current item finished; queue the next episode if it's a series."""
        i = self.identity
        db.clear_progress(i["imdb"], i.get("season", 0), i.get("episode", 0))
        self.advanced = True
        nxt = self._next_episode(i)
        if nxt:
            db.set_next_up(nxt["imdb"], "series", nxt["season"], nxt["episode"],
                           nxt["name"], nxt["poster"])
        return nxt

    def onPlayBackPaused(self):
        self.save()

    def onPlayBackStopped(self):
        self.save()
        self.identity = None

    def onPlayBackEnded(self):
        identity = self.identity
        self.identity = None
        if not identity:
            return
        # Only treat as "finished" if we actually watched to near the end. A
        # failed/instant-ended playback (dead link) must NOT clear the resume point.
        if not (self.advanced or self.last_ratio > 0.9):
            return
        # Mark finished + queue "next up" in Continue Watching. Starting the next
        # episode is Kodi's job now: it autoplays the next-episode item main.py
        # queued into the video playlist, so there's no popup here.
        self.identity = identity  # _advance() reads self.identity
        if not self.advanced:
            self._advance()
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
