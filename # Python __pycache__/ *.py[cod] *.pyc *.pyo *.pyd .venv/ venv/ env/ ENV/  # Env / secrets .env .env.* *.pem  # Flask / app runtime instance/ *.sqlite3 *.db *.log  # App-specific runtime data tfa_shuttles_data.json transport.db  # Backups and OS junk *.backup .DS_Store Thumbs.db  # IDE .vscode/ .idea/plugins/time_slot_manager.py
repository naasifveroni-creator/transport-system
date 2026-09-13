import sqlite3
from datetime import datetime


class TimeSlotManager:
    def __init__(self, db_path="transport.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS global_time_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot TEXT UNIQUE NOT NULL,
                    enabled INTEGER DEFAULT 1
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS campaign_time_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    UNIQUE(campaign, slot)
                )
            """)
            conn.commit()

    def get_global_settings(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT slot, enabled FROM global_time_slots ORDER BY slot")
            rows = cur.fetchall()
        return [{"slot": r[0], "enabled": bool(r[1])} for r in rows]

    def set_global_slot(self, slot, enabled=True):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO global_time_slots (slot, enabled) VALUES (?, ?) "
                "ON CONFLICT(slot) DO UPDATE SET enabled=excluded.enabled",
                (slot, 1 if enabled else 0)
            )
            conn.commit()

    def get_campaign_slots(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT campaign, slot, enabled FROM campaign_time_slots ORDER BY campaign, slot")
            rows = cur.fetchall()
        return [{"campaign": r[0], "slot": r[1], "enabled": bool(r[2])} for r in rows]

    def set_campaign_slot(self, campaign, slot, enabled=True):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO campaign_time_slots (campaign, slot, enabled) VALUES (?, ?, ?) "
                "ON CONFLICT(campaign, slot) DO UPDATE SET enabled=excluded.enabled",
                (campaign, slot, 1 if enabled else 0)
            )
            conn.commit()
