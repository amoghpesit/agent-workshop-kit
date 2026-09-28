"""
server.py - The backend web server for Cafe Nilgiri.

Pure Python standard library - NOTHING to pip install.
Start it with:      python server.py
Then open:          http://localhost:8000

REST API
  GET  /api/health                           -> server status and agent mode
  GET  /api/menu?q=&veg=1&max_price=         -> search the menu
  GET  /api/orders/<id>                      -> order status
  GET  /api/availability?date=&time=&party_size=
  GET  /api/bookings?date=                   -> list bookings (staff view)
  POST /api/bookings                         -> create a booking (JSON body)
  POST /api/chat                             -> talk to the AI agent (JSON body)
"""
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")


def load_env_file():
    """Tiny .env loader: KEY=value lines. Keeps secrets out of the code."""
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

import agent  # noqa: E402  (imported after .env is loaded)
import tools  # noqa: E402
from db import init_db  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    server_version = "CafeNilgiri/1.0"

    # ---------- helpers ----------
    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 100_000:
            raise ValueError("Request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def log_message(self, fmt, *args):
        # Short, readable request log in the terminal
        sys.stdout.write(f"  {self.command:<5} {self.path}  ->  {args[1] if len(args) > 1 else ''}\n")

    # ---------- GET ----------
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        path = url.path.rstrip("/") or "/"

        if path == "/api/health":
            cfg = agent.config()
            return self.send_json({"status": "ok", "agent_mode": agent.current_mode(),
                                   "model": cfg["model"] if agent.current_mode() == "llm" else None,
                                   "tools": [t["function"]["name"] for t in tools.TOOL_SCHEMAS]})
        if path == "/api/menu":
            return self.send_json(tools.search_menu(
                query=q.get("q", ""), veg_only=q.get("veg") in ("1", "true"),
                max_price=q.get("max_price") or None, category=q.get("category", "")))
        if path.startswith("/api/orders/"):
            result = tools.run_tool("get_order_status", {"order_id": path.split("/")[-1]})
            status = 400 if "error" in result else (200 if result.get("found") else 404)
            return self.send_json(result, status)
        if path == "/api/availability":
            result = tools.run_tool("check_table_availability", {
                "date": q.get("date", "today"), "time": q.get("time", ""),
                "party_size": q.get("party_size", "2")})
            return self.send_json(result, 400 if "error" in result else 200)
        if path == "/api/bookings":
            return self.send_json(tools.list_bookings(q.get("date")))
        if path == "/api/tools":
            return self.send_json(tools.TOOL_SCHEMAS)
        if path.startswith("/api/"):
            return self.send_json({"error": "Not found"}, 404)
        return self.serve_static(path)

    # ---------- POST ----------
    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        try:
            body = self.read_json()
        except (ValueError, json.JSONDecodeError) as e:
            return self.send_json({"error": f"Invalid JSON: {e}"}, 400)

        if path == "/api/bookings":
            result = tools.run_tool("create_booking", body)
            return self.send_json(result, 400 if "error" in result else 201)

        if path == "/api/chat":
            # Accept only user/assistant text from the browser. The browser must
            # never be able to send a "system" message or fake tool results.
            history = []
            for m in (body.get("messages") or [])[-12:]:
                if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
                    history.append({"role": m["role"], "content": m["content"][:2000]})
            if not history or history[-1]["role"] != "user":
                return self.send_json({"error": "Last message must be from the user."}, 400)
            return self.send_json(agent.run_agent(history))

        # EXERCISE 4: add  POST /api/bookings/<id>/cancel  here
        return self.send_json({"error": "Not found"}, 404)

    # ---------- static files (the website) ----------
    def serve_static(self, path):
        if path == "/":
            path = "/index.html"
        file_path = os.path.normpath(os.path.join(PUBLIC_DIR, path.lstrip("/")))
        if not file_path.startswith(PUBLIC_DIR + os.sep) or not os.path.isfile(file_path):  # block ../ tricks
            self.send_response(404)
            self.end_headers()
            return
        with open(file_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(file_path)[0] or "application/octet-stream")
                         + ("; charset=utf-8" if file_path.endswith((".html", ".css", ".js")) else ""))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    mode = agent.current_mode()
    print("=" * 60)
    print("  Cafe Nilgiri backend is running")
    print(f"  Website  : http://localhost:{port}")
    print(f"  API      : http://localhost:{port}/api/health")
    print(f"  Agent    : {mode.upper()} mode" + (f" ({agent.config()['model']})" if mode == "llm" else
                                                  "  (add LLM_API_KEY to .env for a real LLM)"))
    print("  Stop with Ctrl+C")
    print("=" * 60)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
