"""TorBox device-code authorization.

No key typing on a remote. We ask TorBox to start a device-code flow, show the
user a short code + URL, then poll until they approve it on their phone. The
returned token is stored via config and used as the TorBox bearer thereafter.
"""
import json
import urllib.error
import urllib.request

from . import config
from .http import HttpError, default_headers, get_json, log

API = "https://api.torbox.app/v1/api"


def device_start(app: str = "torus") -> dict:
    """Kick off the flow. Returns code / device_code / verification_url / interval."""
    return get_json(f"{API}/user/auth/device/start", {"app": app}).get("data", {})


def device_poll(device_code: str) -> dict:
    """Ask whether the device code has been authorized yet.

    While pending/denied TorBox returns a non-2xx; we treat that as "not yet".
    """
    body = json.dumps({"device_code": device_code}).encode("utf-8")
    request = urllib.request.Request(
        f"{API}/user/auth/device/token",
        data=body,
        headers=default_headers({"Content-Type": "application/json"}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return {"success": False}
    except Exception as exc:  # noqa: BLE001 - transient network; keep polling
        log(f"device poll error: {exc}")
        return {"success": False}


def _extract_token(response: dict) -> str:
    data = response.get("data") or {}
    if isinstance(data, str):
        return data
    return data.get("token") or data.get("auth_token") or data.get("api_key") or ""


def run_device_auth() -> bool:
    """Drive the whole flow with a Kodi progress dialog. Returns True on success."""
    import xbmc
    import xbmcgui

    try:
        info = device_start()
    except HttpError as exc:
        xbmcgui.Dialog().ok("Torus", f"Could not start TorBox login:\n{exc}")
        return False

    device_code = info.get("device_code", "")
    code = info.get("code", "")
    url = info.get("friendly_verification_url") or info.get("verification_url", "")
    interval = max(int(info.get("interval", 5)), 2)
    if not device_code:
        xbmcgui.Dialog().ok("Torus", "TorBox did not return a device code. Try again.")
        return False

    dialog = xbmcgui.DialogProgress()
    dialog.create(
        "Link your TorBox account",
        f"1.  On your phone or computer, open:\n     [B]{url}[/B]\n\n"
        f"2.  Enter this code:  [B]{code}[/B]\n\n"
        "Waiting for authorization…",
    )

    monitor = xbmc.Monitor()
    max_wait_seconds = 300
    attempts = max_wait_seconds // interval

    for index in range(attempts):
        if dialog.iscanceled() or monitor.abortRequested():
            dialog.close()
            return False
        dialog.update(int((index / attempts) * 100))
        if monitor.waitForAbort(interval):
            dialog.close()
            return False

        token = _extract_token(device_poll(device_code))
        if token:
            config.set_torbox_token(token)
            dialog.close()
            xbmcgui.Dialog().notification(
                "Torus", "TorBox linked ✓", xbmcgui.NOTIFICATION_INFO
            )
            return True

    dialog.close()
    xbmcgui.Dialog().ok("Torus", "Login timed out. Please try again.")
    return False
