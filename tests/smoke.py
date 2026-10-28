#!/usr/bin/env python3
"""End-to-end smoke test for a running PocketLily server (real LilyPond).

Usage: python3 tests/smoke.py http://localhost:8090 <token>
Exits non-zero on the first failed check. Standard library only.
"""
import json
import re
import sys
import urllib.error
import urllib.request
import zlib

BASE, TOKEN = sys.argv[1].rstrip("/"), sys.argv[2]
passed = 0


def req(method, path, body=None, token=True, raw=False):
    r = urllib.request.Request(BASE + "/" + path, data=body, method=method)
    if token:
        r.add_header("X-Token", TOKEN)
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            data = resp.read()
            return resp.status, (data if raw else json.loads(data or b"{}"))
    except urllib.error.HTTPError as e:
        data = e.read()
        return e.code, (data if raw else json.loads(data or b"{}"))


def check(cond, what, extra=""):
    global passed
    if not cond:
        print(f"FAIL: {what}\n{extra}")
        sys.exit(1)
    passed += 1
    print(f"ok   {what}")


def pdf_text(pdf):
    """Raw PDF plus every Flate stream decompressed (links may sit in object streams)."""
    out = [pdf]
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            out.append(zlib.decompress(m.group(1)))
        except zlib.error:
            pass
    return b"\n".join(out)


SCORE = rb"""\version "2.24.0"
\header { title = "Smoke test" tagline = ##f }
\score {
  \new Staff { c'4 d' e' f' }
  \header { piece = "A. first" }
  \layout { }
  \midi { }
}
\score {
  \new Staff { g'1 }
  \header { piece = "B. second" }
  \layout { }
  \midi { }
}
"""

MUSICXML = b"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><key><fifths>-1</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
    </measure>
  </part>
</score-partwise>
"""

# --- web app and access control ---------------------------------------------
st, page = req("GET", "", token=False, raw=True)
check(st == 200 and b"PocketLily" in page, "web app is served")
st, pdfjs = req("GET", "static/pdf.min.js", token=False, raw=True)
check(st == 200 and len(pdfjs) > 100_000, "PDF.js is bundled in the image")
st, _ = req("GET", "api/files", token=False)
check(st == 401, "API refuses requests without the token")
st, _ = req("PUT", "api/files/..%2Fescape.ly", b"x")
check(st in (400, 404), "path traversal in file names is refused")
st, _ = req("GET", "out/..%2F..%2Fetc/passwd", token=False, raw=True)
check(st != 200, "path traversal in output URLs is refused")

# --- build: PDF + one MIDI per \score, with point-and-click links -------------
st, r = req("PUT", "api/files/smoke.ly", SCORE)
check(st == 200 and r.get("ok"), "save a score")
st, r = req("POST", "api/build/smoke.ly")
check(st == 200 and r.get("ok"), "build succeeds", r.get("log", ""))
outs = r["outputs"]
check(outs == ["smoke/smoke-1.midi", "smoke/smoke.midi", "smoke/smoke.pdf"], "one PDF + one MIDI per score", outs)
st, pdf = req("GET", "out/smoke/smoke.pdf", raw=True)
check(st == 200 and pdf.startswith(b"%PDF"), "PDF is downloadable")
check(b"textedit://" in pdf_text(pdf), "PDF contains point-and-click links (long-press to source)")
st, midi = req("GET", "out/smoke/smoke-1.midi?t=" + TOKEN, token=False, raw=True)
check(st == 200 and midi.startswith(b"MThd"), "MIDI is downloadable with ?t= token")

# --- a failed build keeps the last good outputs and reports the line ----------
bad = SCORE.replace(b"g'1", b"g'1 \\nosuchcommand")
req("PUT", "api/files/smoke.ly", bad)
st, r = req("POST", "api/build/smoke.ly")
check(st == 200 and not r["ok"], "a broken score fails to build")
check(re.search(r"smoke\.ly:\d+:\d+: error", r["log"]) is not None, "log gives file:line:col of the error", r["log"])
check(len(r["outputs"]) == 3, "last good PDF/MIDI are kept after a failed build", r["outputs"])

# --- a score whose name ends in -2 must not mix outputs with smoke.ly ---------
req("PUT", "api/files/smoke-2.ly", SCORE)
st, r = req("POST", "api/build/smoke-2.ly")
check(r.get("ok") and r["outputs"][-1] == "smoke-2/smoke-2.pdf", "outputs are kept per score (out/<name>/)", r)
st, r = req("GET", "api/files/smoke.ly")
check(len(r["outputs"]) == 3, "the other score's outputs are untouched", r["outputs"])

# --- version history -----------------------------------------------------------
st, r = req("GET", "api/history/smoke.ly")
check(st == 200 and len(r["versions"]) >= 1, "saving keeps the previous version", r)
vid = r["versions"][0]["id"]
st, r = req("GET", f"api/history/smoke.ly/{vid}")
check(st == 200 and "Smoke test" in r["content"], "an old version can be read back")

# --- MusicXML import ------------------------------------------------------------
st, r = req("POST", "api/import/My%20Song%20(1).musicxml", MUSICXML)
check(st == 200 and r.get("ok") and r["name"] == "My_Song_1.ly", "MusicXML import creates a cleaned-up .ly", r)
st, r = req("POST", "api/build/My_Song_1.ly")
check(r.get("ok"), "the converted score builds", r.get("log", ""))

# --- delete ---------------------------------------------------------------------
st, r = req("DELETE", "api/files/smoke-2.ly")
check(st == 200 and r.get("ok"), "delete a score")
st, r = req("GET", "api/files")
names = [f["name"] for f in r["files"]]
check("smoke-2.ly" not in names and "smoke.ly" in names, "deleted score is gone, others remain", names)
st, r = req("GET", "api/history/smoke-2.ly")
check(len(r["versions"]) >= 1, "a deleted score keeps a copy in the history")

print(f"\nAll {passed} checks passed.")
