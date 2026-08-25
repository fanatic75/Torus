# Torus

A **TorBox-native media browser for Kodi** with a Stremio-like feel and local-first resume.

Browse movies and TV, find instantly-playable **TorBox-cached** sources, play them in Kodi's
native player, and **resume where you left off** — all stored locally. No accounts to create, no
API keys to enter, no remote sync server, and no scraper zoo to configure.

## Why

Existing Kodi debrid addons bury a great backend under a clunky, directory-first UI and a fragile
mesh of scrapers and Trakt sync. Torus is deliberately narrow: **one polished loop** —
`browse → Play → best cached TorBox source → play → resume later` — built specifically around
TorBox and a home-theater box (CoreELEC / AM6B+).

## Features

- **No API keys anywhere.** Metadata is keyless; TorBox is linked with a phone-approved device
  code (nothing to type on a remote).
- **Keyless discovery** via Cinemeta: Popular / Top-Rated / New / Search, for movies and TV.
- **One-click Play** that auto-picks the best cached source, plus **Choose source** for a ranked
  list with quality, size, and release-group tier labels.
- **Two source providers, merged.** Comet and Torrentio are queried in parallel and their results
  deduped — wider coverage, and resilient if one host is slow or down.
- **Quality-aware ranking** biased for home theater: resolution › source (REMUX › BluRay › WEB-DL)
  › **release-group tier** › HDR/Dolby Vision › lossless audio.
- **Resume + Continue Watching**, keyed by IMDb id (never the torrent), so it survives torrents
  rotating out of cache. Resume reuses the exact source for a fast, position-accurate restart.
- **TV Up Next.** Finishing an episode advances the show in Continue Watching to the next episode
  (across season boundaries), and offers a "Play next?" prompt as each episode ends.
- **Works behind ISP DNS blocks** (e.g. Jio/Airtel blocking metadata hosts in India) with zero
  network config — hosts are resolved over DoH and images proxied.

## How it works

```
Cinemeta        → keyless, IMDb-keyed metadata (catalogs, search, artwork)
  ↓ (imdb id)
Providers       → Comet + Torrentio (queried in parallel, merged) with your TorBox key
  ↓                return TorBox-cached streams, already resolved to playable URLs
Ranking         → resolution › REMUX › group tier (TRaSH) › DV/HDR › lossless audio
  ↓
Kodi player     → plays the URL (Comet → TorBox CDN)
  ↓
SQLite (local)  → resume position + Continue Watching, keyed by IMDb id
```

Nothing is scraped locally and no server is required. Metadata comes from **Cinemeta** (Stremio's
public, keyless metadata API), and source discovery, TorBox cache-checking, and stream resolution
are all done by the hosted provider. Watch-state is keyed on **IMDb id, never on the torrent
hash** — so if a cached release disappears, resume still works against whatever's cached next.

## Requirements

- Kodi **21 (Omega)** — developed and tested on CoreELEC.
- A **paid TorBox account** (linked in-app via device code — no key typing).

That's it. No TMDB key, no metadata signup.

## Install

First, allow third-party addons: **Settings → System → Add-ons → Unknown sources → On**.

### Option A — repository (recommended, auto-updates)

1. **Settings → File manager → Add source**, enter this URL and name it `Torus`:
   `https://raw.githubusercontent.com/fanatic75/Torus/main/repo/`
2. **Add-ons → Install from zip file → Torus → repository.torus →** `repository.torus-1.0.0.zip`.
3. **Add-ons → Install from repository → Torus Repository → Video add-ons → Torus → Install.**

You'll get new versions automatically from then on.

### Option B — single zip (no auto-updates)

Download `repo/plugin.video.torus/plugin.video.torus-<version>.zip` from this repo and use
**Add-ons → Install from zip file**. (The plain GitHub "Download ZIP" of the repo will *not*
install — Kodi needs the inner folder named `plugin.video.torus`, which only the packaged zip has.)

### Then

Open Torus and choose **🔗 Link your TorBox account** — approve the short code shown, on your
phone at `tor.box/link`. Done.

## Configuration

Nothing is mandatory to type. Optional settings:

- **Source provider** — Comet + Torrentio merged (default), or either one alone.
- **Route posters via proxy** — on by default; keeps posters loading behind ISP-blocked image
  hosts.
- **Auto-delete old resume points** — off by default (Continue Watching just shows the 40 most
  recent). When on, prunes resume points untouched for the configured number of days.
- **Advanced** — optional manual TMDB / TorBox key overrides (not needed for normal use).

## Architecture

```
Torus/                       (repo root == the addon; deployed as plugin.video.torus)
├── addon.xml                # plugin + background service declarations
├── main.py                  # router / UI entry point
├── service.py               # background player-monitor (resume engine)
└── resources/
    ├── settings.xml          # settings (string IDs live in language/)
    ├── language/             # strings.po (settings labels)
    └── lib/
        ├── cinemeta.py       # keyless, IMDb-keyed metadata (catalogs/search/detail)
        ├── http.py           # DoH-resolving HTTP client (defeats ISP DNS blocks)
        ├── auth.py           # TorBox device-code login (no key typing)
        ├── config.py         # settings + local token/config
        ├── providers/        # source adapters (Comet, Torrentio) + parallel merge
        ├── ranking.py        # quality scoring
        ├── release_groups.py # TRaSH Guides release-group tiers
        ├── db.py             # SQLite: resume progress + Continue Watching
        └── kodi/             # ListItem / view builders
```

## Development

```bash
git clone <this-repo> Torus && cd Torus
# for local testing, copy the example and add your own keys (this file is gitignored):
cp dev.config.example.json dev.config.json
```

Deploy to a CoreELEC/Kodi box over SSH and watch logs:

```bash
TORUS_BOX=root@<box-ip> ./deploy.sh
ssh root@<box-ip> 'tail -f /storage/.kodi/temp/kodi.log | grep -i torus'
```

Kodi caches addon Python modules per session, so after changing library code restart Kodi
(`systemctl restart kodi`) to load it; `main.py` re-runs on each navigation.

## Disclaimer

Torus is a client for services you configure and pay for (TorBox) and public metadata (Cinemeta).
It hosts no content and ships no indexers. Use it in accordance with the terms of the services you
connect and the laws of your jurisdiction.

## Credits

- **[TRaSH Guides](https://trash-guides.info)** — release-group quality tiers used to rank
  reputable scene/p2p groups. Torus bundles a curated snapshot of their group tier lists.
- **[Cinemeta](https://www.stremio.com/)** (Stremio) — keyless metadata.
- **[Comet](https://github.com/g0ldyy/comet)** and **Torrentio** — Stremio-protocol source
  providers.

## License

[MIT](LICENSE) © 2026 Prateek Banga
