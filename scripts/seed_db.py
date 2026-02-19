# Folder: firetiger-demo/scripts/seed_db.py
# Run once to set up the SQLite database with test data.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlite3
import random
import config

def seed():
    conn = sqlite3.connect(config.DB_PATH)
    
    conn.executescript("""
        DROP TABLE IF EXISTS sellers;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS cart_items;
        
        CREATE TABLE sellers (
            id INTEGER PRIMARY KEY,
            name TEXT,
            tax_rate REAL
        );
        
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price REAL,
            seller_id INTEGER,
            FOREIGN KEY (seller_id) REFERENCES sellers(id)
        );
        
        CREATE TABLE cart_items (
            id INTEGER PRIMARY KEY,
            cart_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
    """)
    
    # 20 sellers
    for i in range(1, 21):
        conn.execute(
            "INSERT INTO sellers VALUES (?, ?, ?)",
            (i, f"Seller {i}", round(random.uniform(0.05, 0.15), 3))
        )
    
    # 150 products spread across sellers
    for i in range(1, 151):
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            (i, f"Product {i}", round(random.uniform(9.99, 99.99), 2), 
             random.randint(1, 20))
        )
    
    # 100 cart items in cart 1 (this makes N+1 very visible)
    for i in range(1, 101):
        conn.execute(
            "INSERT INTO cart_items VALUES (?, 1, ?, ?)",
            (i, i, random.randint(1, 5))
        )
    
    conn.commit()
    conn.close()
    
    print("✅ Database seeded:")
    print("   - 20 sellers")
    print("   - 150 products")
    print("   - 100 cart items in cart_id=1")
    print(f"   - Database: {config.DB_PATH}")


if __name__ == "__main__":
    seed()