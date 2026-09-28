"""
db.py - The data layer for Cafe Nilgiri.

Uses SQLite (built into Python, no installation needed). The database file
`cafe.db` is created automatically the first time the server starts.

Run `python db.py --reset` to wipe it and reload the sample data.
"""
import datetime
import os
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cafe.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dictionaries
    return conn


MENU = [
    # (name, category, price, veg, spicy, available, description)
    ("Filter Coffee", "Beverages", 40, 1, 0, 1, "Classic South Indian filter coffee, served in a davara-tumbler."),
    ("Nilgiri Tea", "Beverages", 35, 1, 0, 1, "Single-estate Nilgiri tea, brewed strong."),
    ("Masala Chai", "Beverages", 30, 1, 0, 1, "Tea with ginger, cardamom and a hint of pepper."),
    ("Cold Coffee", "Beverages", 90, 1, 0, 1, "Chilled coffee blended with ice cream."),
    ("Tender Coconut Mojito", "Beverages", 80, 1, 0, 1, "Tender coconut water with mint and lime."),
    ("Ghee Podi Dosa", "Mains", 90, 1, 1, 1, "Crisp dosa with gunpowder podi and ghee."),
    ("Millet Pongal", "Mains", 100, 1, 0, 1, "Foxtail millet pongal with coconut chutney."),
    ("Veg Biryani", "Mains", 160, 1, 1, 1, "Seeraga samba rice biryani with vegetables."),
    ("Chicken Biryani", "Mains", 210, 0, 1, 1, "Coimbatore-style seeraga samba chicken biryani."),
    ("Egg Kothu Parotta", "Mains", 150, 0, 1, 1, "Shredded parotta tossed with egg and salna."),
    ("Paneer Tikka Wrap", "Wraps", 140, 1, 1, 1, "Tandoori paneer, onions and mint mayo in a wrap."),
    ("Chicken Chettinad Wrap", "Wraps", 170, 0, 1, 1, "Chettinad pepper chicken in a wheat wrap."),
    ("Mushroom Pepper Fry", "Starters", 150, 1, 1, 0, "Button mushrooms with crushed black pepper."),
    ("Ragi Cookies (4 pcs)", "Desserts", 60, 1, 0, 1, "Crunchy finger-millet cookies with jaggery."),
    ("Brownie with Ice Cream", "Desserts", 120, 1, 0, 1, "Warm chocolate brownie with vanilla ice cream."),
]

ORDERS = [
    # (id, customer, items, total, status, eta_minutes)
    ("1021", "Arun", "2 x Filter Coffee, 1 x Ghee Podi Dosa", 170, "preparing", 20),
    ("1022", "Divya", "1 x Chicken Biryani, 1 x Tender Coconut Mojito", 290, "out_for_delivery", 12),
    ("1023", "Karthik", "1 x Paneer Tikka Wrap", 140, "delivered", 0),
    ("1024", "Meena", "2 x Veg Biryani", 320, "cancelled", 0),
]


def init_db(reset=False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    fresh = not os.path.exists(DB_PATH)
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, category TEXT NOT NULL, price INTEGER NOT NULL,
            veg INTEGER NOT NULL, spicy INTEGER NOT NULL, available INTEGER NOT NULL,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY, customer TEXT, items TEXT, total INTEGER,
            status TEXT, eta_minutes INTEGER, placed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL,
            party_size INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'confirmed',
            created_at TEXT NOT NULL
        );
        """
    )
    if fresh:
        cur.executemany(
            "INSERT INTO menu (name, category, price, veg, spicy, available, description) VALUES (?,?,?,?,?,?,?)",
            MENU,
        )
        now = datetime.datetime.now().isoformat(timespec="minutes")
        cur.executemany(
            "INSERT INTO orders (id, customer, items, total, status, eta_minutes, placed_at) VALUES (?,?,?,?,?,?,?)",
            [o + (now,) for o in ORDERS],
        )
        # A few existing bookings so that some slots are already busy.
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        seed = []
        for i in range(6):  # tomorrow 19:00 is almost full (6 of 8 tables)
            seed.append((f"Guest{i+1}", "9000000000", tomorrow.isoformat(), "19:00", 4, "confirmed", now))
        for i in range(8):  # tomorrow 20:00 is completely full
            seed.append((f"Guest{i+7}", "9000000000", tomorrow.isoformat(), "20:00", 2, "confirmed", now))
        cur.executemany(
            "INSERT INTO bookings (name, phone, date, time, party_size, status, created_at) VALUES (?,?,?,?,?,?,?)",
            seed,
        )
    conn.commit()
    conn.close()
    return fresh


if __name__ == "__main__":
    init_db(reset="--reset" in sys.argv)
    print("Database ready at", DB_PATH)
