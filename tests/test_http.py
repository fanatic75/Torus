"""The reachability probe used to skip dead auto-pick sources."""
from resources.lib import http


class _Resp:
    def __init__(self, status):
        self.status = status


class _Conn:
    def __init__(self, status=None, boom=False):
        self._status, self._boom = status, boom

    def request(self, *a, **k):
        if self._boom:
            raise TimeoutError("timed out")

    def getresponse(self):
        return _Resp(self._status)

    def close(self):
        pass


def _patch(monkeypatch, status=None, boom=False):
    monkeypatch.setattr(http, "resolve", lambda host: ["1.2.3.4"])
    monkeypatch.setattr(http, "_PinnedHTTPSConnection",
                        lambda host, ip, timeout: _Conn(status, boom))


def test_reachable_true_on_206(monkeypatch):
    _patch(monkeypatch, status=206)
    assert http.reachable("https://host/stream") is True


def test_reachable_true_on_redirect(monkeypatch):
    _patch(monkeypatch, status=302)
    assert http.reachable("https://host/stream") is True


def test_reachable_false_on_404(monkeypatch):
    _patch(monkeypatch, status=404)
    assert http.reachable("https://host/stream") is False


def test_reachable_false_on_timeout(monkeypatch):
    _patch(monkeypatch, boom=True)
    assert http.reachable("https://host/stream") is False


def test_reachable_false_when_dns_fails(monkeypatch):
    monkeypatch.setattr(http, "resolve", lambda host: [])
    assert http.reachable("https://host/stream") is False
