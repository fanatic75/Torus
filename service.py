"""Torus background service.

Declared as an xbmc.service extension point, this runs for the whole Kodi
session. In M5 it becomes the resume engine: a subclassed xbmc.Player that
listens to playback callbacks and persists position/duration to SQLite,
keyed by imdb_id + season + episode.

M0 scope: prove the service starts and shuts down cleanly. It just logs and
idles until Kodi asks it to abort.
"""
import xbmc


class TorusMonitor(xbmc.Monitor):
    """Session monitor. Hook onSettingsChanged etc. here later."""


# --- M5 preview (kept here so the shape is obvious; wired up later) ---------
# class TorusPlayer(xbmc.Player):
#     def onAVStarted(self):
#         # look up saved resume position for the currently-playing media and seek
#         ...
#     def onPlayBackStopped(self):
#         # persist final position to SQLite
#         ...
# ---------------------------------------------------------------------------


def main() -> None:
    monitor = TorusMonitor()
    xbmc.log("[Torus] service started", xbmc.LOGINFO)

    # Idle loop; waitForAbort doubles as our sleep and shutdown signal.
    while not monitor.abortRequested():
        if monitor.waitForAbort(10):
            break

    xbmc.log("[Torus] service stopped", xbmc.LOGINFO)


if __name__ == "__main__":
    main()
