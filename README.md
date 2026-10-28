# PocketLily

*LilyPond in your pocket.*

Edit [LilyPond](https://lilypond.org) scores from your phone or tablet, tap a button, and get
the engraved PDF and MIDI back — built on your own small server (a Raspberry Pi is plenty).

PocketLily is a self-hosted web app: a ~330-line Python server (standard library only) running
LilyPond in a locked-down Docker container, and a single HTML page you open in the browser of any
device on your network.

## Features

- **Edit** `.ly` files in the browser; **⚙ Build** saves and runs LilyPond on the server.
- **Score view** with PDF pages drawn on the device: pinch to zoom, **tap for full-screen reading**
  (the screen stays on), **long-press a note to jump to its line in the source**.
- **Errors**: a failed build puts the cursor on the offending line; the last good PDF stays visible.
- **MIDI tab**: one player, one entry per `\score` with `\midi`, named after its `piece` header
  or the section `\markup` above it.
- **MusicXML import** (`.mxl`, `.musicxml`, `.xml`, e.g. exported from MuseScore), converted with
  LilyPond's `musicxml2ly`.
- **Shared library**: files live on the server, so phone, tablet and computer see the same scores
  (and you can also edit them with any tool that reaches the folder: Samba, File Browser, scp…).
- **Version history**: the last 20 versions of each score (one every 5 minutes at most) can be
  restored from the app; deleted scores are kept there too.
- **New** scores start from a template (C major piano score with chord names and Roman
  numerals) — or from your own `template.ly`.
- **Per-device settings**: page quality, editor text size, what to show after a build or when
  opening a file, screen wake, dark pages.

## How it works

```
 phone / tablet / PC (browser)                server (Docker)
 ┌─────────────────────────┐   HTTP (LAN)   ┌──────────────────────────────────┐
 │ static/index.html       │ ─────────────▶ │ server.py  ──▶  lilypond         │
 │ editor · PDF.js viewer  │ ◀───────────── │            ──▶  musicxml2ly      │
 │ MIDI player             │   PDF / MIDI   │ /scores: *.ly, out/, .history/   │
 └─────────────────────────┘                └──────────────────────────────────┘
```

## Quick start

Requirements: a Linux machine with Docker and Docker Compose (Raspberry Pi 4/5 with a 64-bit OS,
or any amd64 PC/NAS). Images are published for `linux/arm64` and `linux/amd64`.

```bash
mkdir pocketlily && cd pocketlily
curl -fsSLO https://raw.githubusercontent.com/rousselmanu/pocketlily/main/docker-compose.yml
curl -fsSL  https://raw.githubusercontent.com/rousselmanu/pocketlily/main/.env.example -o .env
nano .env            # set LILY_TOKEN (e.g. `openssl rand -hex 16`) and UID_GID (`echo $(id -u):$(id -g)`)
mkdir -p scores      # your .ly files go here
docker compose up -d
```

Open `http://<server-ip>:8090` on your phone, enter the token once, then use the browser menu
**Add to Home screen**. Copy existing `.ly` files into `scores/`, or use the import button.

Or build the image yourself: `git clone` this repository, uncomment `build: .` in
`docker-compose.yml` and run `docker compose up -d --build`.

## Using it

| Where | Action | Result |
|---|---|---|
| Toolbar | ⚙ | save and build |
| Toolbar | file / upload / save / trash icons | new score, import `.ly` or MusicXML, save, delete |
| Score | tap | full-screen reading (tap again or *back* to exit) |
| Score | pinch | zoom 1×–4× |
| Score | long-press (right-click on a computer) | jump to that note in the source |
| Editor | Ctrl+S / Ctrl+Enter | save / build (hardware keyboard) |
| Status bar | tap | open the build log |
| **More** tab | | build log, downloads, previous versions, settings |

MIDI files are numbered by LilyPond in `\score` order (`name.midi`, `name-1.midi`, …). To give each
one a clear name in the MIDI tab, add `\header { piece = "…" }` to the score, or put a section
title in a `\markup` just before it.

## Configuration

Environment variables (in `docker-compose.yml` / `.env`):

| Variable | Default | Meaning |
|---|---|---|
| `LILY_TOKEN` | *(empty)* | access token; asked once per device. Empty disables it (not recommended) |
| `BUILD_TIMEOUT` | `180` | seconds before a LilyPond run is killed |
| `LILY_BACKEND` | `cairo` | `cairo`: LilyPond writes the PDF itself (faster, no Ghostscript); `ps`: classic PostScript + Ghostscript |
| `KEEP_VERSIONS` | `20` | previous versions kept per score |
| `VERSION_MINUTES` | `5` | minimum minutes between two saved versions of a score |
| `UID_GID` | `1000:1000` | user the container runs as; should own `./scores` |

Settings in the app (**More → Settings**) are stored per device, in the browser.

## Security — read this

A LilyPond file is a program: **a `.ly` file can run arbitrary code (Scheme) on the server**.
PocketLily is meant for your own scores on your own network.

- Keep port 8090 on your **LAN**, or reach it through a **VPN** (WireGuard, Tailscale…).
  **Do not expose it to the internet**, not even behind a reverse proxy with HTTPS.
- Set a long `LILY_TOKEN`. It only keeps other devices of your network out; over plain HTTP it
  can be read by anyone who can see your traffic.
- The provided compose file runs the container read-only, as an unprivileged user, without
  capabilities, with memory and process limits. Keep these settings.

## Files on disk

```
scores/
├── my_piece.ly           your scores (and .ily include files)
├── template.ly           optional: used by "New" instead of the built-in template
├── out/my_piece/         generated my_piece.pdf, my_piece.midi, my_piece-1.midi …
└── .history/             previous versions: my_piece.ly.YYYYmmdd-HHMMSS
```

## Updating

```bash
docker compose pull && docker compose up -d
```

## Development

The server needs only Python 3 and LilyPond:

```bash
SCORES_DIR=./scores PORT=8090 python3 server.py      # then open http://localhost:8090
```

PDF.js is downloaded into the image at build time; for local development without Docker, put
`pdf.min.js` and `pdf.worker.min.js` (PDF.js 3.11.174) in `static/`.

Tests: `tests/smoke.sh` starts the image with the production hardening and runs
`tests/smoke.py` against it (build, errors, MIDI naming, point-and-click links, MusicXML
import, history, path traversal). GitHub Actions runs it on every push and pull request, and
publishes the multi-arch image to GitHub Container Registry from `main` and from `v*` tags.

## Limitations

- Served over plain HTTP on the LAN, so browsers treat it as a shortcut rather than a fully
  installable offline app.
- The MIDI player and the screen-wake helper are loaded from a CDN: the device needs internet
  access for MIDI playback (downloading the `.midi` file works offline).
- Mainly tested with Chrome on Android; the long-press gesture relies on the browser's
  context-menu event (right-click on desktop).
- One build at a time (by design, to stay gentle with a Raspberry Pi).

## Licence

MIT — see [LICENSE](LICENSE). LilyPond and the other components keep their own licences, see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
