"""Phoenix Product API.

A small product catalogue + cart API for the Phoenix electronics store.
- Uses PostgreSQL when DATABASE_URL is set, otherwise an in-file SQLite DB
  (handy for local runs and unit tests).
- Exposes Prometheus metrics at /metrics (hand-rolled, no extra dependency).
- ERROR_RATE (0.0-1.0) lets us simulate a bad release for the Argo Rollouts
  canary-failure demo (Day 9 / capstone).
"""
import os
import random
import sqlite3
import threading
import time

from flask import Flask, Response, g, jsonify, request

APP_VERSION = os.getenv("APP_VERSION", "dev")
ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
SQLITE_PATH = os.getenv("SQLITE_PATH", "/tmp/phoenix.db")

SEED_PRODUCTS = [
    ("Phoenix X1 Smartphone", "Phones", 24999.0, 50),
    ("Phoenix Book 14 Laptop", "Laptops", 58999.0, 20),
    ("Phoenix Buds Pro", "Audio", 3999.0, 200),
    ("Phoenix Watch S", "Wearables", 7999.0, 75),
    ("Phoenix 55\" 4K TV", "TVs", 41999.0, 10),
    ("Phoenix Power Bank 20000mAh", "Accessories", 1499.0, 300),
]

app = Flask(__name__)

# ---------------------------------------------------------------- metrics ---
_lock = threading.Lock()
_requests = {}  # (method, path, status) -> count
_latency_sum = {}  # path -> seconds
_latency_count = {}  # path -> count


def _record(method, path, status, seconds):
    with _lock:
        key = (method, path, str(status))
        _requests[key] = _requests.get(key, 0) + 1
        _latency_sum[path] = _latency_sum.get(path, 0.0) + seconds
        _latency_count[path] = _latency_count.get(path, 0) + 1


def render_metrics():
    lines = [
        "# HELP phoenix_http_requests_total Total HTTP requests.",
        "# TYPE phoenix_http_requests_total counter",
    ]
    with _lock:
        for (method, path, status), n in sorted(_requests.items()):
            lines.append(
                f'phoenix_http_requests_total{{method="{method}",path="{path}",'
                f'status="{status}",version="{APP_VERSION}"}} {n}'
            )
        lines += [
            "# HELP phoenix_http_request_duration_seconds Request latency.",
            "# TYPE phoenix_http_request_duration_seconds summary",
        ]
        for path in sorted(_latency_sum):
            lines.append(f'phoenix_http_request_duration_seconds_sum{{path="{path}"}} {_latency_sum[path]:.6f}')
            lines.append(f'phoenix_http_request_duration_seconds_count{{path="{path}"}} {_latency_count[path]}')
    lines += [
        "# HELP phoenix_app_info Build information.",
        "# TYPE phoenix_app_info gauge",
        f'phoenix_app_info{{version="{APP_VERSION}"}} 1',
    ]
    return "\n".join(lines) + "\n"


@app.before_request
def _start_timer():
    g.start = time.time()


@app.after_request
def _after(resp):
    path = request.url_rule.rule if request.url_rule else "unmatched"
    if path != "/metrics":
        _record(request.method, path, resp.status_code, time.time() - g.start)
    return resp


# --------------------------------------------------------------- database ---
class DB:
    """Tiny wrapper so the same SQL works on Postgres and SQLite."""

    def __init__(self):
        self.pg = bool(DATABASE_URL)

    def connect(self):
        if self.pg:
            import psycopg2  # imported lazily so tests don't need it

            return psycopg2.connect(DATABASE_URL)
        conn = sqlite3.connect(SQLITE_PATH)
        return conn

    def q(self, sql):
        return sql.replace("?", "%s") if self.pg else sql

    def execute(self, sql, params=(), fetch=False):
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(self.q(sql), params)
            rows = cur.fetchall() if fetch else None
            conn.commit()
            return rows
        finally:
            conn.close()

    def init(self):
        pk = "SERIAL PRIMARY KEY" if self.pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        self.execute(
            f"CREATE TABLE IF NOT EXISTS products (id {pk}, name TEXT NOT NULL, "
            "category TEXT NOT NULL, price REAL NOT NULL, stock INTEGER NOT NULL)"
        )
        self.execute(
            f"CREATE TABLE IF NOT EXISTS cart_items (id {pk}, session_id TEXT NOT NULL, "
            "product_id INTEGER NOT NULL, quantity INTEGER NOT NULL)"
        )
        count = self.execute("SELECT COUNT(*) FROM products", fetch=True)[0][0]
        if count == 0:
            for p in SEED_PRODUCTS:
                self.execute(
                    "INSERT INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)", p
                )


db = DB()
_initialised = False


def ensure_db():
    global _initialised
    if not _initialised:
        db.init()
        _initialised = True


def product_row(r):
    return {"id": r[0], "name": r[1], "category": r[2], "price": r[3], "stock": r[4]}


# ----------------------------------------------------------------- routes ---
def maybe_fail():
    """Simulate a broken release when ERROR_RATE > 0."""
    if ERROR_RATE > 0 and random.random() < ERROR_RATE:
        return jsonify({"error": "simulated failure", "version": APP_VERSION}), 500
    return None


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "version": APP_VERSION})


@app.get("/readyz")
def readyz():
    try:
        ensure_db()
        db.execute("SELECT 1", fetch=True)
        return jsonify({"status": "ready"})
    except Exception as exc:  # pragma: no cover - only when DB is down
        return jsonify({"status": "not ready", "error": str(exc)}), 503


@app.get("/metrics")
def metrics():
    return Response(render_metrics(), mimetype="text/plain; version=0.0.4")


@app.get("/api/version")
def version():
    return jsonify({"version": APP_VERSION})


@app.get("/api/products")
def list_products():
    failed = maybe_fail()
    if failed:
        return failed
    ensure_db()
    category = request.args.get("category")
    if category:
        rows = db.execute("SELECT * FROM products WHERE category = ? ORDER BY id", (category,), fetch=True)
    else:
        rows = db.execute("SELECT * FROM products ORDER BY id", fetch=True)
    return jsonify([product_row(r) for r in rows])


@app.get("/api/products/<int:pid>")
def get_product(pid):
    failed = maybe_fail()
    if failed:
        return failed
    ensure_db()
    rows = db.execute("SELECT * FROM products WHERE id = ?", (pid,), fetch=True)
    if not rows:
        return jsonify({"error": "not found"}), 404
    return jsonify(product_row(rows[0]))


@app.get("/api/cart/<session_id>")
def get_cart(session_id):
    ensure_db()
    rows = db.execute(
        "SELECT p.id, p.name, p.price, c.quantity FROM cart_items c "
        "JOIN products p ON p.id = c.product_id WHERE c.session_id = ? ORDER BY c.id",
        (session_id,),
        fetch=True,
    )
    items = [{"product_id": r[0], "name": r[1], "price": r[2], "quantity": r[3]} for r in rows]
    total = round(sum(i["price"] * i["quantity"] for i in items), 2)
    return jsonify({"session_id": session_id, "items": items, "total": total})


@app.post("/api/cart/<session_id>")
def add_to_cart(session_id):
    ensure_db()
    body = request.get_json(silent=True) or {}
    pid = body.get("product_id")
    qty = int(body.get("quantity", 1))
    if not isinstance(pid, int) or qty < 1:
        return jsonify({"error": "product_id (int) and quantity >= 1 required"}), 400
    if not db.execute("SELECT id FROM products WHERE id = ?", (pid,), fetch=True):
        return jsonify({"error": "product not found"}), 404
    db.execute(
        "INSERT INTO cart_items (session_id, product_id, quantity) VALUES (?, ?, ?)",
        (session_id, pid, qty),
    )
    resp = get_cart(session_id)
    resp.status_code = 201
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
