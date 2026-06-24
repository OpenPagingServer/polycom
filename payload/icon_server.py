
import mimetypes
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent
MODULE_LOG_DIR = Path(os.getenv("OPS_ENDPOINT_MODULE_LOG_DIR", "/var/log/openpagingserver/endpointmodules"))
LOG_FILE = MODULE_LOG_DIR / "polycom" / "icon_server.log"
DEBUG = os.getenv("DEBUG", "").strip().lower() == "true"
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

server = None
thread = None
active_port = None


def debug_log(message):
    if not DEBUG:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def asset_dirs():
    paths = []
    configured = os.getenv("ASSET_PATH", "").strip()
    if configured:
        paths.append(Path(configured))
    paths.append(Path("/var/lib/openpagingserver/assets"))
    paths.append(ROOT_DIR / "web" / "assets")
    unique = []
    seen = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def resolve_icon(name):
    safe_name = Path(name).name
    if not safe_name:
        return None
    stem = Path(safe_name).stem
    for directory in asset_dirs():
        if not directory.exists():
            continue
        exact = directory / safe_name
        if exact.is_file() and exact.suffix.lower() in ALLOWED_SUFFIXES:
            return exact
        matches = []
        for candidate in directory.iterdir():
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if candidate.stem == stem:
                matches.append(candidate)
        if matches:
            matches.sort()
            return matches[0]
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/icon":
            debug_log(f"request path={parsed.path} status=404")
            self.send_error(404)
            return
        name = parse_qs(parsed.query).get("name", [""])[0]
        icon_path = resolve_icon(name)
        if icon_path is None:
            debug_log(f"request icon={name!r} status=404")
            self.send_error(404)
            return
        try:
            data = icon_path.read_bytes()
        except OSError as exc:
            debug_log(f"request icon={name!r} path={icon_path} status=500 error={exc}")
            self.send_error(500)
            return
        content_type, _ = mimetypes.guess_type(str(icon_path))
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        return


def start():
    global server, thread, active_port
    if server is not None:
        return active_port
    preferred = int(os.getenv("POLYCOM_ICON_PORT", "16976"))
    last_error = None
    for port in range(preferred, preferred + 20):
        try:
            candidate = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            server = candidate
            active_port = port
            os.environ["POLYCOM_ICON_PORT_ACTIVE"] = str(port)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            debug_log(f"icon_server started port={port}")
            return active_port
        except OSError as exc:
            debug_log(f"icon_server bind failed port={port} error={exc}")
            last_error = exc
    raise last_error


def stop():
    global server, thread, active_port
    if server is None:
        return
    server.shutdown()
    server.server_close()
    debug_log(f"icon_server stopped port={active_port}")
    server = None
    active_port = None
    os.environ.pop("POLYCOM_ICON_PORT_ACTIVE", None)
    if thread is not None:
        thread.join(timeout=1)
        thread = None
