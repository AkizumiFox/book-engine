"""
Build System Dev Server
=======================
Serves the website locally, rebuilds when sources or engine files change, and reloads
open pages. Standard library only.

Pages built by the server include a small script that listens on /__reload
(server-sent events); a normal build does not include it.
"""

import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .book import Book, ENGINE_ROOT
from .html import build_html
from .utils import print_step, print_success, print_error, print_info

POLL_SECONDS = 0.5


class ReloadHub:
    """Tracks a build counter; SSE clients are told whenever it increases."""

    def __init__(self):
        self.generation = 0
        self.condition = threading.Condition()

    def notify(self):
        with self.condition:
            self.generation += 1
            self.condition.notify_all()

    def wait_for_change(self, seen: int, timeout: float) -> int:
        with self.condition:
            self.condition.wait_for(lambda: self.generation != seen, timeout=timeout)
            return self.generation


def _handler(book: Book, hub: ReloadHub):
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/__reload":
                return super().do_GET()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            seen = hub.generation
            try:
                while True:
                    current = hub.wait_for_change(seen, timeout=15)
                    if current != seen:
                        self.wfile.write(b"data: reload\n\n")
                        seen = current
                    else:
                        self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def end_headers(self):
            # Always revalidate, so reloads show the new build
            if self.path != "/__reload":
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def log_message(self, format, *args):
            pass

    return partial(Handler, directory=str(book.html_dir))


def _watched_files(book: Book) -> dict[Path, float]:
    roots = [book.src_dir, ENGINE_ROOT / "filters", ENGINE_ROOT / "templates" / "html", book.macros_file,
             book.config_file] + [c.directory for c in book.chapters]
    if isinstance(book.overlay_source, (str, Path)):
        roots.append(Path(book.overlay_source))
    snapshot = {}
    for root in roots:
        paths = [root] if root.is_file() else (root.rglob("*") if root.is_dir() else [])
        for path in paths:
            if path.is_file():
                try:
                    snapshot[path] = path.stat().st_mtime
                except OSError:
                    pass
    return snapshot


def serve(book: Book, port: int = 8000):
    print_step("Initial build...")
    build_html(book, dev_reload=True)

    hub = ReloadHub()
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(book, hub))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print_success(f"Serving {book.html_dir} at http://127.0.0.1:{port}/  (Ctrl+C to stop)")

    snapshot = _watched_files(book)
    try:
        while True:
            time.sleep(POLL_SECONDS)
            current = _watched_files(book)
            if current == snapshot:
                continue
            changed = sorted({p for p in current.keys() | snapshot.keys() if current.get(p) != snapshot.get(p)})
            print_info("Changed: " + ", ".join(str(p.relative_to(book.root)) if p.is_relative_to(book.root)
                                               else str(p) for p in changed[:5]))
            snapshot = current
            try:
                # A fresh Book picks up config edits and added or removed pages
                book = Book(book.root, overlay=book.overlay_source)
                if build_html(book, dev_reload=True):
                    hub.notify()
            except Exception as e:  # keep serving after a broken edit
                print_error(f"Rebuild failed: {e}")
            snapshot = _watched_files(book)
    except KeyboardInterrupt:
        print_info("Stopped.")
    finally:
        server.shutdown()
