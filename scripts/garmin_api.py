#!/usr/bin/env python3
"""
garmin_api.py — HTTP sidecar exposing Garmin data to n8n.

n8n HTTP Request node calls: GET http://garmin-api:8765/fetch
Auto-saves raw JSON to /training/data/today.json for the Claude Code scheduled agent.

Endpoints:
  GET /fetch   — run garmin_fetch.py, return JSON, save to /training/data/today.json
  GET /health  — liveness check
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
import sys
import json
import os
import pathlib

PORT = int(os.getenv("GARMIN_API_PORT", 8765))
DATA_DIR = pathlib.Path("/training/data")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/fetch":
            self._handle_fetch()
        elif self.path == "/health":
            self._respond(200, b'{"status":"ok"}')
        else:
            self._respond(404, b'{"error":"not found"}')

    def _handle_fetch(self):
        result = subprocess.run(
            [sys.executable, "/app/garmin_fetch.py"],
            capture_output=True,
            text=True,
            cwd="/app",
        )
        if result.returncode != 0:
            body = json.dumps({"error": "fetch failed", "stderr": result.stderr}).encode()
            self._respond(500, body)
            return

        # Auto-save for debugging and as fallback for the scheduled agent
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / "today.json").write_text(result.stdout)
        except Exception as e:
            sys.stderr.write(f"[garmin-api] WARNING: could not save today.json: {e}\n")

        self._respond(200, result.stdout.encode())

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        sys.stderr.write(f"[garmin-api] {self.address_string()} - {format % args}\n")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[garmin-api] Listening on :{PORT}", flush=True)
    server.serve_forever()
