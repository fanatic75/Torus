"""Torus background service — the resume engine.

Runs for the whole Kodi session. When Torus starts playback it stashes the media
identity (imdb/season/episode) in a window property; this service reads it, then
periodically and on pause/stop persists the play position to SQLite (keyed by
IMDb id, never the torrent). That's what powers Resume and Continue Watching.
"""
import json
from urllib.parse import urlencode

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
        # Playback failed to OPEN (dead/too-slow link, expired, no network). This
        # fires only on a genuine failure — never on a user-initiated stop — so
        # it's safe to auto-retry the next-best source. Resume point is untouched.
        identity = self._read_identity()
        self.identity = None
        self._retry_next_source(identity)

    def _apply_resume(self, item, identity):
        """Put the stored resume point on a retry item so it picks up where the
        failed source left off (or where the user last watched)."""
        try:
            prog = db.get_progress(identity.get("imdb", ""),
                                   identity.get("season", 0), identity.get("episode", 0))
        except Exception:  # noqa: BLE001
            prog = None
        if prog and prog.get("duration"):
            ratio = prog["position"] / prog["duration"]
            if 0.01 < ratio < 0.95:
                duration = float(prog["duration"])
                resume_at = max(0.0, float(prog["position"]) - 10)
                item.setProperty("ResumeTime", str(resume_at))
                item.setProperty("TotalTime", str(duration))

    def _retry_next_source(self, identity):
        """When a source fails to open, play the next of the fallbacks main.py
        stashed (top 3, Torrentio-preferred), carrying the resume point."""
        if not identity:
            return
        candidates = identity.get("candidates") or []
        idx = identity.get("cand_idx", 0) + 1
        if idx >= len(candidates):
            if candidates:  # we had fallbacks but they're exhausted
                xbmcgui.Dialog().notification(
                    "Torus", "Couldn't play — no working source",
                    xbmcgui.NOTIFICATION_WARNING)
            return
        next_url = candidates[idx]
        item = xbmcgui.ListItem(path=next_url)
        self._apply_resume(item, identity)
        state = dict(identity)
        state["url"] = next_url
        state["cand_idx"] = idx
        xbmcgui.Window(HOME).setProperty(PLAYING_PROP, json.dumps(state))
        xbmc.log(f"[Torus] source failed, retrying fallback {idx}", xbmc.LOGINFO)
        self.play(next_url, item)
        # Playing a single URL replaces the video playlist, wiping the next-episode
        # pointer main.py queued — so re-queue it, or a retried episode would lose
        # autoplay-next / the ⏭ button.
        self._requeue_next_episode(identity)

    def _requeue_next_episode(self, identity):
        if identity.get("mtype") != "series":
            return
        nxt = self._next_episode(identity)
        if not nxt:
            return
        url = "plugin://plugin.video.torus/?" + urlencode({
            "action": "play", "imdb": nxt["imdb"], "mtype": "series",
            "season": nxt["season"], "episode": nxt["episode"]})
        pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        if any(pl[i].getPath() == url for i in range(len(pl))):
            return
        li = xbmcgui.ListItem(label="S%02dE%02d" % (nxt["season"], nxt["episode"]))
        li.setProperty("IsPlayable", "true")
        pl.add(url, li)

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
