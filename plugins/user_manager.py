import sqlite3
from werkzeug.security import generate_password_hash


class UserManager:
    def __init__(self, db_path="transport.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    name TEXT,
                    password TEXT,
                    is_admin INTEGER DEFAULT 0,
                    is_driver INTEGER DEFAULT 0,
                    registered_address TEXT DEFAULT '',
                    travel_allowance REAL DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS drivers (
                    username TEXT PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    license_plate TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    driver_id TEXT,
                    date_time TEXT,
                    pickup TEXT,
                    dropoff TEXT,
                    status TEXT
                )
            """)
            conn.commit()

    def get_all_users(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT username, name, is_admin, is_driver, registered_address, travel_allowance FROM users")
            rows = cur.fetchall()
        return [
            {
                "username": r[0], "name": r[1],
                "is_admin": bool(r[2]), "is_driver": bool(r[3]),
                "registered_address": r[4], "travel_allowance": r[5]
            }
            for r in rows
        ]

    def get_user(self, username):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT username, name, is_admin, is_driver, registered_address, travel_allowance FROM users WHERE username=?", (username,))
            r = cur.fetchone()
        if not r:
            return None
        return {
            "username": r[0], "name": r[1],
            "is_admin": bool(r[2]), "is_driver": bool(r[3]),
            "registered_address": r[4], "travel_allowance": r[5]
        }

    def create_user(self, username, name, password, is_admin=False, is_driver=False, registered_address=""):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, name, password, is_admin, is_driver, registered_address) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (username, name, generate_password_hash(password),
                 1 if is_admin else 0, 1 if is_driver else 0, registered_address)
            )
            conn.commit()

    def delete_user(self, username):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE username=?", (username,))
            conn.commit()
