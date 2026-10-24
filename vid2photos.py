#!/usr/bin/env python3
import os
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BREW = os.environ.get("VID2PHOTOS_BIN", "/opt/homebrew/bin")
YTDLP = f"{BREW}/yt-dlp"
FFMPEG = f"{BREW}/ffmpeg"
FFPROBE = f"{BREW}/ffprobe"
PORT = int(os.environ.get("VID2PHOTOS_PORT", "7201"))
HOST = os.environ.get("VID2PHOTOS_HOST", "127.0.0.1")
TOKEN_FILE = os.path.expanduser(os.environ.get("VID2PHOTOS_TOKEN_FILE", "~/.config/vid2photos/token"))
MAX_HEIGHT = os.environ.get("VID2PHOTOS_MAX_HEIGHT", "1080")
DL_TIMEOUT = 600  # seconds; a long YouTube video at 1080p fits comfortably

# Photos plays H.264/HEVC in MP4. Prefer avc1 so no transcode is needed; the
# post-download codec check below catches VP9/AV1 fallbacks and re-encodes them.
FORMAT = (
    f"bv*[ext=mp4][vcodec^=avc1][height<={MAX_HEIGHT}]+ba[ext=m4a]"
    f"/bv*[ext=mp4][height<={MAX_HEIGHT}]+ba[ext=m4a]"
    f"/b[ext=mp4][height<={MAX_HEIGHT}]/b"
)

PLAYABLE = {"h264", "hevc"}


def read_token():
    try:
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
            if not token:
                sys.exit("vid2photos: token file is empty")
            return token
    except OSError:
        sys.exit("vid2photos: token file unavailable; see README.md")


TOKEN = None  # Loaded only at startup, allowing offline imports and tests.


def log(msg):
    print(msg, flush=True)


def run(cmd, timeout=DL_TIMEOUT):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def video_codec(path):
    p = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", path], 60)
    return p.stdout.strip().split("\n")[0] if p.returncode == 0 else ""


def is_mp4(path):
    p = run([FFPROBE, "-v", "error", "-show_entries",
             "format=format_name:format_tags=major_brand", "-of", "json", path], 60)
    if p.returncode != 0:
        return False
    try:
        fmt = json.loads(p.stdout).get("format", {})
        brand = fmt.get("tags", {}).get("major_brand", "").strip()
        return "mp4" in fmt.get("format_name", "").split(",") and (
            brand.startswith("iso") or brand in {"mp41", "mp42", "avc1", "dash", "M4V", "MSNV"}
        )
    except (ValueError, AttributeError):
        return False


def safe_filename(title):
    name = re.sub(r"[^\w\s.-]", "", title, flags=re.UNICODE).strip()
    name = re.sub(r"\s+", " ", name)[:80].strip(" .")
    return name or "video"


def download(url, start, end, workdir):
    """Return (path, filename). Raises RuntimeError with a short message."""
    cmd = [YTDLP, "--no-playlist", "--no-progress", "-f", FORMAT,
           "--merge-output-format", "mp4",
           "-o", os.path.join(workdir, "out.%(ext)s"),
           "--print-to-file", "%(title)s", os.path.join(workdir, "title.txt")]
    if start is not None or end is not None:
        section = f"*{start or 0}-{end if end is not None else 'inf'}"
        cmd += ["--download-sections", section, "--force-keyframes-at-cuts"]
    cmd.append(url)
    p = run(cmd)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-3:])
        raise RuntimeError(f"yt-dlp failed:\n{tail}")

    out = os.path.join(workdir, "out.mp4")
    if not os.path.exists(out):
        files = [f for f in os.listdir(workdir) if f.startswith("out.")]
        if not files:
            raise RuntimeError("yt-dlp produced no file")
        out = os.path.join(workdir, files[0])

    codec = video_codec(out)
    if codec not in PLAYABLE:
        # VP9/AV1/anything else: re-encode once so Photos can actually play it.
        fixed = os.path.join(workdir, "fixed.mp4")
        p = run([FFMPEG, "-y", "-v", "error", "-i", out,
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                 "-movflags", "+faststart", fixed])
        if p.returncode != 0:
            raise RuntimeError(f"transcode failed ({codec}): {p.stderr.strip()[-300:]}")
        out = fixed

    elif not is_mp4(out):
        # A playable codec can still be in MKV/MOV: explicitly remux to MP4.
        fixed = os.path.join(workdir, "fixed.mp4")
        p = run([FFMPEG, "-y", "-v", "error", "-i", out,
                 "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy",
                 "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                 "-f", "mp4", fixed])
        if p.returncode != 0:
            raise RuntimeError("MP4 remux failed")
        out = fixed

    if not is_mp4(out):
        raise RuntimeError("output is not a verified MP4 container")

    try:
        with open(os.path.join(workdir, "title.txt")) as f:
            title = f.read().strip().splitlines()[-1]
    except (OSError, IndexError):
        title = "video"
    suffix = ""
    if start is not None or end is not None:
        suffix = f" ({start or 0}s-{end if end is not None else 'end'}s)"
    return out, safe_filename(title + suffix) + ".mp4"


def parse_seconds(v):
    if v in (None, ""):
        return None
    try:
        n = float(v)
    except ValueError:
        raise ValueError(f"not a number of seconds: {v!r}")
    if not math.isfinite(n) or n < 0:
        raise ValueError("seconds must be finite and >= 0")
    return int(n) if n.is_integer() else n


class Handler(BaseHTTPRequestHandler):
    server_version = "vid2photos/1"

    def log_message(self, fmt, *args):
        # BaseHTTPRequestHandler passes raw malformed request lines to this hook.
        # Suppress both access and parser-error details rather than risk tokens.
        pass

    def send_text(self, code, body):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        if code >= 400:  # the Shortcut branches on this extension; see docs/shortcut.md
            self.send_header("Content-Disposition", 'attachment; filename="error.txt"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self, q):
        auth = self.headers.get("Authorization", "")
        if TOKEN and auth.startswith("Bearer ") and auth[7:].strip() == TOKEN:
            return True
        return bool(TOKEN) and q.get("token", [""])[0] == TOKEN

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/health":
            return self.send_text(200, "ok\n")
        if parsed.path != "/dl":
            return self.send_text(404, "not found\n")
        if not self.authorized(q):
            return self.send_text(401, "unauthorized\n")

        url = q.get("url", [""])[0].strip()
        if not re.match(r"^https?://", url):
            log("bad url parameter")
            return self.send_text(400, "url must be an http(s) link\n")
        try:
            start, end = parse_seconds(q.get("s", [None])[0]), parse_seconds(q.get("e", [None])[0])
            if start is not None and end is not None and end <= start:
                raise ValueError("e must be greater than s")
        except ValueError as e:
            return self.send_text(400, f"{e}\n")

        log("download requested")
        workdir = tempfile.mkdtemp(prefix="vid2photos-")
        try:
            try:
                path, filename = download(url, start, end, workdir)
            except subprocess.TimeoutExpired:
                return self.send_text(504, f"download exceeded {DL_TIMEOUT}s\n")
            except RuntimeError as e:
                log("download failed")
                return self.send_text(502, f"{e}\n")

            size = os.path.getsize(path)
            log(f"serving video ({size} bytes)")
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''"
                             + urllib.parse.quote(filename))
            self.end_headers()
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1 << 20)
        except (BrokenPipeError, ConnectionResetError):
            log("client went away")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind calls socket.getfqdn() on the bind address; on
        # macOS that reverse lookup of 0.0.0.0 can hang for minutes, so the
        # agent sat with a socket in CLOSED state and never listened.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "vid2photos", self.server_address[1]


def main():
    global TOKEN
    TOKEN = read_token()
    for tool in (YTDLP, FFMPEG, FFPROBE):
        if not os.access(tool, os.X_OK):
            sys.exit(f"vid2photos: missing {tool}")
    httpd = Server((HOST, PORT), Handler)
    log(f"vid2photos listening on {HOST}:{PORT} (max height {MAX_HEIGHT})")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
