"""Does a provider's release actually belong to the title we asked for?

Providers like Comet resolve an IMDb id to a title and then search indexers by
TEXT, so a common-word title ("Dark") drags in other shows ("Dark Matter",
"His Dark Materials"). We don't drop those (a valid release may be named oddly);
instead ranking uses this to float genuine matches to the top — which is what
one-click Play and the next-episode auto-pick select.

The test is strict on purpose: the release's show/movie name (the part before
the SxxExx marker, or before the year for a movie) must EQUAL the expected title
after normalising. That rejects "Dark Matter" for "Dark" while keeping "Dark".
"""
from __future__ import annotations
import re

_EP = re.compile(r"(s\d{1,2}[ ._-]?e\d{1,2}|\d{1,2}x\d{2})", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Lowercase, drop punctuation and standalone year tokens, collapse spaces."""
    text = _NON_ALNUM.sub(" ", (text or "").lower())
    text = _YEAR.sub(" ", text)
    return " ".join(text.split())


def release_show_title(release: str, series: bool) -> str:
    """The show/movie name portion of a release: text before the SxxExx marker
    (series) or before the year (movie), normalised."""
    text = release or ""
    marker = _EP.search(text) if series else _YEAR.search(text)
    if marker:
        text = text[:marker.start()]
    return normalize(text)


def matches(release: str, expected_title: str, series: bool) -> bool:
    """True if the release's show/movie name equals the expected title."""
    expected = normalize(expected_title)
    if not expected:
        return False
    return release_show_title(release, series) == expected
