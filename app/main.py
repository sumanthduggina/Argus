# Folder: firetiger-demo/app/main.py
#
# The Flask web app being monitored.
# Intentionally simple - 3 routes.
# The interesting code is in middleware.py and db.py

from flask import Flask, jsonify
from app.middleware import register_middleware
from app.db import get_checkout_total, get_connection
import config

app = Flask(__name__)

# Register auto-instrumentation - this is all you need
# Every request is now automatically tracked
register_middleware(app)


@app.route("/checkout")
def checkout():
    """
    The route we're going to break.
    In fast mode: ~10ms (1 DB query)
    In slow mode: ~600ms (101+ DB queries - N+1 problem)
    """
    result = get_checkout_total(cart_id=1)
    return jsonify(result)


@app.route("/products")
def products():
    """Simple products list - should always be fast"""
    conn = get_connection()
    rows = conn.execute("SELECT id, name, price FROM products LIMIT 20").fetchall()
    conn.close()
    return jsonify({"products": [dict(r) for r in rows]})


@app.route("/health")
def health():
    """Health check - used by verifier to confirm app is up after deploy"""
    return jsonify({
        "status": "ok",
        "slow_mode": config.USE_SLOW_QUERY
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=config.APP_PORT, debug=False)