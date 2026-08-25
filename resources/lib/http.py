"""Tiny JSON-over-HTTP helper built on the standard library.

Deliberately dependency-free (urllib, not requests) so the addon always loads
without Kodi needing to fetch extra modules.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

try:
    import xbmc

    def log(message: str) -> None:
        xbmc.log(f"[Torus] {message}", xbmc.LOGINFO)

except Exception:

    def log(message: str) -> None:
        print(f"[Torus] {message}")


class HttpError(Exception):
    """Raised when a request fails or returns a non-2xx status."""


# Some hosts (TorBox behind Cloudflare) 403 the default "Python-urllib" UA, so
# every request carries an explicit User-Agent.
USER_AGENT = "Torus/0.1 (Kodi)"


def default_headers(extra: dict | None = None) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if extra:
        headers.update(extra)
    return headers


def get_json(url: str, params: dict | None = None,
             headers: dict | None = None, timeout: int = 20) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers=default_headers(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise HttpError(f"HTTP {exc.code} for {url}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HttpError(f"Request failed for {url}: {exc}") from exc
