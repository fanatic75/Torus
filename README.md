# Torus

A **TorBox-native media browser for Kodi** with a Stremio-like feel and local-first resume.

Browse movies and TV via TMDB, find instantly-playable **TorBox-cached** sources through
Stremio-protocol providers (Comet, Torrentio), play in Kodi's native player, and **resume where
you left off** — all stored locally. No accounts, no remote sync server, no scraper zoo to
configure.

> Status: **early development.** See the [Roadmap](#roadmap). Currently at M0 (installable skeleton).

## Why

Existing Kodi debrid addons bury a great backend under a clunky, directory-first UI and a fragile
mesh of scrapers and Trakt sync. Torus is deliberately narrow: **one polished loop** —
`browse → Play → best cached TorBox source → play → resume later` — built specifically around
TorBox and a home-theater box (CoreELEC / AM6B+).

## How it works

```
Cinemeta        → keyless, IMDb-keyed metadata (catalogs, search, artwork)
  ↓ (imdb id)
Provider        → Stremio-protocol addon (Comet/Torrentio) with your TorBox key
  ↓                returns TorBox-cached streams, already resolved to playable URLs
Ranking         → prefer REMUX > WEB-DL, DV/FEL > HDR10, TrueHD Atmos, sensible size
  ↓
Kodi player     → plays the URL
  ↓
SQLite (local)  → resume position + continue-watching + watchlist, keyed by IMDb id
```

Nothing is scraped locally and no server is required. Metadata comes from **Cinemeta** (Stremio's
public, keyless metadata API — no API key to sign up for or bundle), and source discovery, TorBox
cache-checking, and URL resolution are all done by the hosted provider. Watch-state is keyed on
**IMDb id, never on the torrent hash**, so a different cached release tomorrow still resumes
correctly. Behind ISP DNS blocks (e.g. TMDB/Cinemeta blocked in India), the addon resolves hosts
over DoH and proxies images, so it works with no network configuration.

## Architecture

```
Torus/                     (repo root == the addon; deployed as plugin.video.torus)
├── addon.xml              # plugin + background service declarations
├── main.py                # router / UI entry point
├── service.py             # background player-monitor (resume engine)
└── resources/
    ├── settings.xml        # provider + quality + optional advanced overrides
    └── lib/
        ├── cinemeta.py     # keyless IMDb-keyed metadata (catalogs/search/detail) [M1]
        ├── http.py         # DoH-resolving HTTP client (defeats ISP DNS blocks)   [M1]
        ├── auth.py         # TorBox device-code login (no key typing)             [M1]
        ├── providers/      # comet, torrentio, ... behind one interface           [M2]
        ├── ranking.py      # release parsing + quality scoring                    [M2/M4]
        ├── db.py           # SQLite (progress, watchlist)                         [M5]
        └── kodi/           # ListItem / view builders                            [M1+]
```

## Requirements

- Kodi **21 (Omega)** — developed/tested against CoreELEC.
- A **paid TorBox account** (linked in-app via device code — no key typing).

No TMDB key, no metadata signup: discovery uses Cinemeta, which is keyless.

## Configuration

There's nothing mandatory to type. On first run, open **🔗 Link your TorBox account** from the
home screen and approve the short code on your phone. Optional settings:

- **Source provider** — Comet (default) or Torrentio.
- **Quality profile** — Cinephile / Balanced / Data Saver.
- **Route posters via proxy** — on by default; helps behind ISP-blocked image hosts.
- Advanced: optional TMDB/TorBox key overrides (not needed for normal use).

## Development

```bash
git clone <this-repo> Torus && cd Torus
# copy the example and fill in your own keys (this file is gitignored):
cp dev.config.example.json dev.config.json
```

Deploy to your box over SSH:

```bash
TORUS_BOX=root@192.168.29.55 ./deploy.sh
```

Watch logs:

```bash
ssh root@192.168.29.55 'tail -f /storage/.kodi/temp/kodi.log | grep -i torus'
```

## Roadmap

- [x] **M0** — installable skeleton (router + service stub + settings)
- [ ] **M1** — TMDB discovery: trending/popular rows, search, movie/show detail
- [ ] **M2** — provider adapter (Comet): list cached sources by IMDb id
- [ ] **M3** — playback: source-select → `setResolvedUrl` → native player
- [ ] **M4** — ranking engine + one-click **Play** / **Choose Source**
- [ ] **M5** — local resume + **Continue Watching** (the service engine)
- [ ] **M6** — TV drill-down (seasons/episodes/next-up) + settings polish

## Disclaimer

Torus is a client for services you configure and pay for (TorBox) and public metadata (TMDB). It
hosts no content and ships no indexers. Use it in accordance with the terms of the services you
connect and the laws of your jurisdiction.

## License

[MIT](LICENSE) © 2026 Prateek Banga
