# Third-party software

PocketLily's own code (`server.py`, `static/`) is MIT-licensed (see `LICENSE`).
It relies on the following third-party software, which keeps its own licence.

## Inside the Docker image

| Component | Licence | How it is used |
|---|---|---|
| [GNU LilyPond](https://lilypond.org) 2.24 (incl. `musicxml2ly`) | GPL-3.0-or-later | Debian package, run as a separate program to engrave scores and convert MusicXML |
| [Debian](https://www.debian.org) bookworm-slim, Python 3, Ghostscript, TeX Gyre and DejaVu fonts | various free licences (see `/usr/share/doc/*/copyright` in the image) | base system, Debian packages |
| [PDF.js](https://github.com/mozilla/pdf.js) 3.11.174 | Apache-2.0 | downloaded from cdnjs at image build time, served to the browser to draw the pages |

The Debian packages in the image are unmodified; their source code is available from
[Debian](https://sources.debian.org) (e.g. `apt-get source lilypond`).

## Loaded by the browser from a CDN (jsDelivr)

| Component | Licence | Used for |
|---|---|---|
| [html-midi-player](https://github.com/cifkao/html-midi-player) 1.5.0 | BSD-2-Clause | MIDI player |
| [@magenta/music](https://github.com/magenta/magenta-js) 1.23.1 | Apache-2.0 | MIDI playback engine and piano sounds |
| [Tone.js](https://github.com/Tonejs/Tone.js) 14.7.58 | MIT | Web Audio |
| [focus-visible](https://github.com/WICG/focus-visible) 5 | W3C Software and Document License | dependency of html-midi-player |
| [NoSleep.js](https://github.com/richtr/NoSleep.js) 0.12.0 | MIT | keeps the screen on in full-screen reading mode |

## Icons

Toolbar icons are drawn after [Lucide](https://lucide.dev) icons (ISC licence):
file-plus, upload, save, trash-2, download, settings.

```
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT).
All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any purpose with or
without fee is hereby granted, provided that the above copyright notice and this permission
notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE
AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```
