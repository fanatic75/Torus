"""JSON-over-HTTPS with DNS-over-HTTPS (DoH) resolution.

Why DoH: some ISPs (e.g. Jio/Airtel in India) DNS-poison metadata hosts, handing
back a dead IP so requests hang. We bypass the system resolver entirely — resolve every
hostname via encrypted DoH to a well-known resolver IP (no system DNS needed for
the resolver itself), then connect straight to the real IP with correct SNI and
full certificate validation. This makes the addon work behind ISP DNS blocks
with zero network configuration.
"""

from __future__ import annotations
import http.client
import json
import os
import socket
import ssl
import time
import urllib.parse

from . import config

try:
    import xbmc

    def log(message: str) -> None:
        xbmc.log(f"[Torus] {message}", xbmc.LOGINFO)

except Exception:

    def log(message: str) -> None:
        print(f"[Torus] {message}")


class HttpError(Exception):
    """Raised when a request fails or returns a non-2xx status."""


USER_AGENT = "Torus/0.1 (Kodi)"

# DoH resolvers reached by fixed anycast IP (so they need no system DNS), each
# with the SNI/host used for TLS validation and its query path.
_DOH_RESOLVERS = [
    ("cloudflare-dns.com", "1.1.1.1", "/dns-query"),
    ("dns.google", "8.8.8.8", "/resolve"),
]

_SSL_CTX = ssl.create_default_context()


def default_headers(extra: dict | None = None) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if extra:
        headers.update(extra)
    return headers


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection to a specific IP while keeping SNI/cert = the real host."""

    def __init__(self, sni_host: str, ip: str, timeout: int):
        super().__init__(sni_host, 443, timeout=timeout, context=_SSL_CTX)
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        # self.host is the SNI host passed to super().__init__ -> correct SNI + cert check.
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


# --- DoH resolution with a small on-disk cache -----------------------------
def _dns_cache_path() -> str:
    return os.path.join(config.profile_dir(), "dns_cache.json")


def _load_dns_cache() -> dict:
    try:
        with open(_dns_cache_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_dns_cache(cache: dict) -> None:
    try:
        with open(_dns_cache_path(), "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
    except Exception:
        pass


def _doh_query(name: str) -> list:
    for sni, ip, path in _DOH_RESOLVERS:
        conn = None
        try:
            conn = _PinnedHTTPSConnection(sni, ip, 8)
            conn.request(
                "GET",
                f"{path}?name={urllib.parse.quote(name)}&type=A",
                headers={"accept": "application/dns-json", "User-Agent": USER_AGENT},
            )
            data = json.loads(conn.getresponse().read().decode("utf-8"))
            ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
            if ips:
                return ips
        except Exception as exc:  # noqa: BLE001 - try the next resolver
            log(f"DoH via {sni} failed for {name}: {exc}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return []


def resolve(host: str) -> list:
    """Return real IPs for host via DoH (cached ~5 min), or system DNS as a last resort."""
    cache = _load_dns_cache()
    now = time.time()
    entry = cache.get(host)
    if entry and entry.get("exp", 0) > now and entry.get("ips"):
        return entry["ips"]

    ips = _doh_query(host)
    if ips:
        cache[host] = {"ips": ips, "exp": now + 300}
        _save_dns_cache(cache)
        return ips

    try:  # DoH unavailable (rare) — fall back to whatever the system returns
        return [socket.gethostbyname(host)]
    except Exception:
        return []


_REDIRECT_STATUS = (301, 302, 303, 307, 308)


def get_json(url: str, params: dict | None = None,
             headers: dict | None = None, timeout: int = 20,
             max_redirects: int = 5) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    for _ in range(max_redirects + 1):
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
        path = parts.path + (f"?{parts.query}" if parts.query else "")

        ips = resolve(host)
        if not ips:
            raise HttpError(f"Could not resolve {host}")

        redirect_to = None
        last_error = None
        for ip in ips:
            conn = None
            try:
                conn = _PinnedHTTPSConnection(host, ip, timeout)
                conn.request("GET", path, headers=default_headers(headers))
                response = conn.getresponse()
                if response.status in _REDIRECT_STATUS:
                    location = response.getheader("Location")
                    response.read()
                    if not location:
                        raise HttpError(f"redirect without Location for {url}")
                    # urljoin handles both absolute and relative Location values.
                    redirect_to = urllib.parse.urljoin(url, location)
                    break
                body = response.read().decode("utf-8")
                if response.status >= 400:
                    raise HttpError(f"HTTP {response.status} for {url}")
                return json.loads(body)
            except HttpError:
                raise
            except Exception as exc:  # noqa: BLE001 - try the next IP
                last_error = exc
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        if redirect_to:
            url = redirect_to
            continue
        raise HttpError(f"Request failed for {url}: {last_error}")

    raise HttpError(f"Too many redirects for {url}")
