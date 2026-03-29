# Folder: firetiger-demo/app/db.py
#
# Two versions of the checkout query:
# - FAST: single JOIN query (normal operation)
# - SLOW: N+1 loop (the bug we introduce)
#
# The middleware tracks how many queries fire,
# so the difference shows up clearly in metrics.


import sqlite3
import time
import config

# This counter is used by middleware to track queries per request
# Gets reset at start of each request
query_counter = {"count": 0, "total_time_ms": 0.0}


def get_connection():
    """Get SQLite connection with row factory for dict-like access"""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def track_query(func):
    """
    Decorator that wraps any DB call and increments the query counter.
    Applied to every DB function so middleware can count automatically.
    """
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = (time.time() - start) * 1000
        
        # Increment global counter - middleware reads this after request
        query_counter["count"] += 1
        query_counter["total_time_ms"] += elapsed
        
        return result
    return wrapper


@track_query
def fetch_cart_items(conn, cart_id):
    return conn.execute(
        "SELECT * FROM cart_items WHERE cart_id = ?", 
        (cart_id,)
    ).fetchall()


@track_query
def fetch_product(conn, product_id):
    """Called once per cart item in slow version = N+1"""
    time.sleep(0.01)
    return conn.execute(
        "SELECT * FROM products WHERE id = ?", 
        (product_id,)
    ).fetchone()


@track_query
def fetch_checkout_fast(conn, cart_id):
    """
    FAST VERSION: Single JOIN query
    This is how checkout should work.
    1 query regardless of how many items in cart.
    """
    return conn.execute("""
        SELECT 
            ci.quantity,
            p.price,
            p.name,
            s.tax_rate
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        JOIN sellers s ON p.seller_id = s.id
        WHERE ci.cart_id = ?
    """, (cart_id,)).fetchall()


def get_checkout_total(cart_id: int) -> dict:
    """
    Main function called by the /checkout route.
    Switches between fast and slow based on USE_SLOW_QUERY env var.
    
    In the demo:
    - Normal operation: USE_SLOW_QUERY=false → fast version
    - Bad deploy:       USE_SLOW_QUERY=true  → slow version (N+1)
    """
    conn = get_connection()
    total = 0.0
    item_count = 0

    if config.USE_SLOW_QUERY:
        # ===================================================
        # SLOW VERSION - N+1 Query Problem
        # ===================================================
        # First query: get all cart items (1 query)
            # ===================================================
    # FAST VERSION - Single JOIN Query
    # ===================================================
    # Everything in one query regardless of cart size
    rows = fetch_checkout_fast(conn, cart_id)
    
    for row in rows:
        price = row["price"] * row["quantity"]
        tax = price * row["tax_rate"]
        total += price + tax
        item_count += 1
    conn.close()
    
    return {
        "total": round(total, 2),
        "item_count": item_count,
        "cart_id": cart_id
    }
# TODO: optimize this loop - added by refactor branch
