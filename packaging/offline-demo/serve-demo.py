"""Serve the extracted FloodGuard static proposal demo on localhost only."""

from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    site_root = Path(__file__).resolve().parent / "site"
    if not (site_root / "public" / "index.html").is_file():
        raise SystemExit("The packaged site is incomplete: public/index.html is missing.")
    os.chdir(site_root)
    server = ThreadingHTTPServer((HOST, PORT), SimpleHTTPRequestHandler)
    print(f"FloodGuard fixture demo: http://{HOST}:{PORT}/public/")
    print("Non-operational. Not an official warning. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
