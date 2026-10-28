#!/usr/bin/env python3
"""PocketLily - tiny LilyPond build server (Python standard library only).

Scores live in SCORES_DIR (*.ly / *.ily). Outputs go to SCORES_DIR/out/<stem>/,
previous versions to SCORES_DIR/.history/.
API (JSON; if LILY_TOKEN is set, send it in the X-Token header):
  GET    api/files                 -> list of scores
  GET    api/files/<name>          -> {"name", "content", "outputs", "stale"}
  PUT    api/files/<name>          -> save body as <name> (previous version kept in .history)
  DELETE api/files/<name>          -> delete <name> and its outputs (a copy stays in .history)
  POST   api/build/<name>          -> run LilyPond: {"ok", "log", "seconds", "outputs"}
  POST   api/import/<file.mxl>     -> MusicXML (.mxl/.musicxml/.xml) -> new .ly (musicxml2ly)
  GET    api/history/<name>        -> saved versions of <name>
  GET    api/history/<name>/<id>   -> content of one version
  GET    out/<stem>/<file>         -> generated PDF / MIDI (token also accepted as ?t=)
  GET    /                         -> web app (static/)
"""
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

SCORES = Path(os.environ.get("SCORES_DIR", "/scores")).resolve()
OUT = SCORES / "out"
STATIC = Path(__file__).resolve().parent / "static"
TOKEN = os.environ.get("LILY_TOKEN", "")
PORT = int(os.environ.get("PORT", "8090"))
TIMEOUT = int(os.environ.get("BUILD_TIMEOUT", "180"))
# "cairo": LilyPond writes the PDF itself (fast, no Ghostscript); "ps": classic PostScript + Ghostscript
BACKEND = os.environ.get("LILY_BACKEND", "cairo")
MAX_BODY = 2 * 1024 * 1024
HIST = SCORES / ".history"                          # previous versions: <name>.<YYYYmmdd-HHMMSS>
KEEP = int(os.environ.get("KEEP_VERSIONS", "20"))   # versions kept per file
GAP = int(os.environ.get("VERSION_MINUTES", "5")) * 60   # at most one version per 5 min

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-. ]{0,100}\.(ly|ily)$")
OUT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-. ]{0,120}\.(pdf|midi?|png|svg)$")
build_lock = threading.Lock()  # one LilyPond at a time (Pi RAM)


def safe_name(name, rx=NAME_RE):
    name = unquote(name)
    if not rx.match(name) or "/" in name or ".." in name:
        return None
    return name


class Handler(BaseHTTPRequestHandler):
    server_version = "pocketlily/1.0"

    # ---------- helpers ----------
    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def send_json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path, cache="no-cache"):
        if not path.is_file():
            return self.send_json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix in (".mid", ".midi"):
            ctype = "audio/midi"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        if not TOKEN:
            return True
        if self.headers.get("X-Token", "") == TOKEN:
            return True
        self.send_json({"error": "bad or missing token"}, 401)
        return False

    def body(self):
        n = int(self.headers.get("Content-Length", "0"))
        if n > MAX_BODY:
            raise ValueError("file too large")
        return self.rfile.read(n)

    def route(self):
        return [p for p in urlparse(self.path).path.split("/") if p]

    # ---------- verbs ----------
    def do_GET(self):
        parts = self.route()
        if not parts or parts == ["index.html"]:
            return self.send_file(STATIC / "index.html")
        if parts[0] == "static" and len(parts) == 2:
            f = (STATIC / unquote(parts[1])).resolve()
            if f.parent != STATIC:
                return self.send_json({"error": "not found"}, 404)
            return self.send_file(f)
        if parts[0] == "manifest.webmanifest":
            return self.send_file(STATIC / "manifest.webmanifest")
        if parts[0] == "out" and len(parts) == 3:
            # outputs are not secret-free if a token is set: accept ?t=<token> too
            q = parse_qs(urlparse(self.path).query)
            if TOKEN and q.get("t", [""])[0] != TOKEN and not self.authorized():
                return
            stem, name = unquote(parts[1]), safe_name(parts[2], OUT_RE)
            if not name or not NAME_RE.match(stem + ".ly") or ".." in stem:
                return self.send_json({"error": "bad name"}, 400)
            return self.send_file(OUT / stem / name)
        if parts[:2] == ["api", "files"]:
            if not self.authorized():
                return
            if len(parts) == 2:
                files = sorted(
                    (
                        {"name": p.name, "mtime": p.stat().st_mtime}
                        for p in SCORES.iterdir()
                        if p.is_file() and NAME_RE.match(p.name)
                    ),
                    key=lambda d: d["name"].lower(),
                )
                return self.send_json({"files": files, "token_required": bool(TOKEN)})
            name = safe_name(parts[2])
            if not name or not (SCORES / name).is_file():
                return self.send_json({"error": "not found"}, 404)
            outs = list_outputs(name) if name.endswith(".ly") else []
            pdfs = [o for o in outs if o.endswith(".pdf")]
            stale = bool(pdfs) and (OUT / pdfs[0]).stat().st_mtime < (SCORES / name).stat().st_mtime
            return self.send_json(
                {"name": name, "content": (SCORES / name).read_text("utf-8", "replace"),
                 "outputs": outs, "stale": stale}
            )
        if parts[:2] == ["api", "history"] and len(parts) in (3, 4):
            if not self.authorized():
                return
            name = safe_name(parts[2])
            if not name:
                return self.send_json({"error": "bad name"}, 400)
            if len(parts) == 3:
                return self.send_json({"versions": [
                    {"id": f.name[len(name) + 1:], "time": f.stat().st_mtime, "size": f.stat().st_size}
                    for f in reversed(versions(name))]})
            vid = unquote(parts[3])
            f = HIST / f"{name}.{vid}"
            if not re.fullmatch(r"\d{8}-\d{6}", vid) or not f.is_file():
                return self.send_json({"error": "not found"}, 404)
            return self.send_json({"name": name, "id": vid, "content": f.read_text("utf-8", "replace")})
        if parts == ["api", "ping"]:
            return self.send_json({"ok": True, "token_required": bool(TOKEN)})
        self.send_json({"error": "not found"}, 404)

    def do_PUT(self):
        parts = self.route()
        if parts[:2] != ["api", "files"] or len(parts) != 3:
            return self.send_json({"error": "not found"}, 404)
        if not self.authorized():
            return
        name = safe_name(parts[2])
        if not name:
            return self.send_json({"error": "invalid file name (letters, digits, - _ . space; ends in .ly)"}, 400)
        try:
            data = self.body()
        except ValueError as e:
            return self.send_json({"error": str(e)}, 413)
        target = SCORES / name
        if target.is_file() and target.read_bytes() == data:
            return self.send_json({"ok": True, "name": name})      # unchanged
        force = "snapshot=1" in (urlparse(self.path).query or "")
        snapshot(name, force=force)
        tmp = SCORES / (".tmp-" + name)
        tmp.write_bytes(data)
        tmp.replace(SCORES / name)
        self.send_json({"ok": True, "name": name})

    def do_DELETE(self):
        parts = self.route()
        if parts[:2] != ["api", "files"] or len(parts) != 3:
            return self.send_json({"error": "not found"}, 404)
        if not self.authorized():
            return
        name = safe_name(parts[2])
        if not name or not (SCORES / name).is_file():
            return self.send_json({"error": "not found"}, 404)
        if name.endswith(".ly"):
            for o in list_outputs(name):
                (OUT / o).unlink(missing_ok=True)
            try:
                (OUT / name[:-3]).rmdir()
            except OSError:
                pass
        snapshot(name, force=True)          # a deleted score stays in .history/
        (SCORES / name).unlink()
        self.send_json({"ok": True})

    def do_POST(self):
        parts = self.route()
        if parts[:2] == ["api", "import"] and len(parts) == 3:
            if not self.authorized():
                return
            try:
                data = self.body()
            except ValueError as e:
                return self.send_json({"error": str(e)}, 413)
            return self.send_json(import_musicxml(unquote(parts[2]), data))
        if parts[:2] != ["api", "build"] or len(parts) != 3:
            return self.send_json({"error": "not found"}, 404)
        if not self.authorized():
            return
        name = safe_name(parts[2])
        if not name or not (SCORES / name).is_file():
            return self.send_json({"error": "not found"}, 404)
        if name.endswith(".ily"):
            return self.send_json({"error": ".ily files are includes; build the .ly that uses them"}, 400)
        self.send_json(build(name))


def versions(name):
    """Saved versions of <name>, oldest first."""
    if not HIST.is_dir():
        return []
    pat = re.compile(re.escape(name) + r"\.\d{8}-\d{6}")
    return sorted(f for f in HIST.iterdir() if pat.fullmatch(f.name))


def snapshot(name, force=False):
    """Copy the current <name> to .history/ before it is overwritten or deleted."""
    src = SCORES / name
    if not src.is_file():
        return
    old = versions(name)
    if old and not force and time.time() - old[-1].stat().st_ctime < GAP:
        return                                  # a recent version already exists
    HIST.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(src.stat().st_mtime))
    dst = HIST / f"{name}.{stamp}"
    if not dst.exists():
        shutil.copy2(src, dst)                  # keeps the time that version was saved
    for f in versions(name)[:-KEEP]:
        f.unlink(missing_ok=True)


def list_outputs(name):
    """Outputs of <name> as "stem/file" paths relative to OUT."""
    stem = name[: -len(".ly")]
    d = OUT / stem
    if not d.is_dir():
        return []
    pat = re.compile(r"^" + re.escape(stem) + r"(-\d+)?\.(pdf|midi?)$")
    return sorted(f"{stem}/{p.name}" for p in d.iterdir() if pat.match(p.name))


XML_EXT = (".mxl", ".musicxml", ".xml")


def clean_stem(stem):
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9_\-.]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip(" ._-") or "imported"
    return stem[:90]


def import_musicxml(orig, data):
    """Convert an uploaded MusicXML (.mxl/.musicxml/.xml) file to <stem>.ly."""
    low = orig.lower()
    ext = next((e for e in XML_EXT if low.endswith(e)), None)
    if not ext:
        return {"ok": False, "log": "", "error": "expected .mxl, .musicxml or .xml"}
    stem = clean_stem(orig[: -len(ext)])
    name, n = stem + ".ly", 2
    while (SCORES / name).exists():          # never overwrite an existing score
        name, n = f"{stem}-{n}.ly", n + 1
    work = Path(tempfile.mkdtemp(prefix="mx-"))
    try:
        src = work / ("in" + ext)
        src.write_bytes(data)
        cmd = ["musicxml2ly", "--npl", "-o", str(work / "out.ly"), str(src)]
        if ext == ".mxl":
            cmd.insert(1, "-z")
        with build_lock:
            try:
                p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=TIMEOUT)
                log = (p.stdout + p.stderr).strip()
            except subprocess.TimeoutExpired:
                return {"ok": False, "log": f"*** musicxml2ly killed after {TIMEOUT}s ***"}
        out = work / "out.ly"
        if p.returncode != 0 or not out.is_file():
            return {"ok": False, "log": log or "musicxml2ly failed"}
        shutil.move(str(out), str(SCORES / name))
        return {"ok": True, "name": name, "log": log}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def build(name):
    stem = name[: -len(".ly")]
    (OUT / stem).mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with build_lock:
        try:
            proc = subprocess.run(
                ["lilypond", f"-dbackend={BACKEND}", "-I", str(SCORES), "-o", str(OUT / stem / stem), str(SCORES / name)],
                cwd=SCORES, capture_output=True, text=True, timeout=TIMEOUT,
            )
            ok, log = proc.returncode == 0, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired as e:
            ok, log = False, (e.stderr or "") + f"\n*** killed after {TIMEOUT}s ***"
            if isinstance(log, bytes):
                log = log.decode("utf-8", "replace")
    if ok:   # drop leftovers of earlier builds (e.g. a removed \midi); on failure keep the last good PDF/MIDI
        for o in list_outputs(name):
            if (OUT / o).stat().st_mtime < t0 - 1:
                (OUT / o).unlink(missing_ok=True)
    return {"ok": ok, "log": log.strip(), "seconds": round(time.time() - t0, 1),
            "outputs": list_outputs(name)}


if __name__ == "__main__":
    SCORES.mkdir(parents=True, exist_ok=True)
    print(f"pocketlily on :{PORT}, scores in {SCORES}, backend {BACKEND}, token {'ON' if TOKEN else 'OFF'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
