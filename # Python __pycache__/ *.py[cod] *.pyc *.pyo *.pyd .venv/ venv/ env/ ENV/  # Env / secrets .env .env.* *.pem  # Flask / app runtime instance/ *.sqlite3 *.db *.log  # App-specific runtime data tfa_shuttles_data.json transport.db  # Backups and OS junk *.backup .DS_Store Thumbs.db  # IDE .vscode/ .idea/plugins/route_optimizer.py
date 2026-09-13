import sqlite3


class RouteOptimizer:
    def __init__(self, db_path="transport.db"):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def get_overview(self):
        overview = {
            "total_routes": 0,
            "optimized_routes": 0,
            "fuel_savings": 0,
            "total_distance": 0,
            "time_savings": 0,
            "optimization_rate": 0
        }
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM bookings")
                overview["total_routes"] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            pass
        return overview

    def optimize(self, bookings):
        """Return bookings sorted by pickup -> dropoff (very basic)."""
        return sorted(bookings, key=lambda b: (b.get("pickup", ""), b.get("dropoff", "")))
