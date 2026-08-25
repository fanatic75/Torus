"""Torus library package.

Modules land here as milestones progress:
    tmdb.py        - discovery, search, detail, external_ids (TMDB -> IMDb)   [M1]
    providers/     - Stremio-protocol source adapters (comet, torrentio, ...) [M2]
    ranking.py     - release-title parsing + quality scoring                  [M4]
    playback.py    - resolve -> setResolvedUrl -> attach resume props         [M3/M5]
    db.py          - SQLite schema + queries (progress, watchlist, cache)     [M5]
    kodi/          - ListItem/view builders                                   [M1+]
"""
