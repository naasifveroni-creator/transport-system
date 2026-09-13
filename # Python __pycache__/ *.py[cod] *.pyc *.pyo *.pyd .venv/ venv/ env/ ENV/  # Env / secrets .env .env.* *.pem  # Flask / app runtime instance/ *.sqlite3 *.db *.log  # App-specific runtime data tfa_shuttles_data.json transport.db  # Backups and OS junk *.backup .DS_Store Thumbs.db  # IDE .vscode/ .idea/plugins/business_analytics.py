import sqlite3


class BusinessAnalytics:
    def __init__(self, db_path="transport.db"):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def get_dashboard_metrics(self):
        metrics = {
            "total_bookings": 0,
            "completed_bookings": 0,
            "in_progress_bookings": 0,
            "unassigned_bookings": 0,
            "total_drivers": 0,
            "total_users": 0,
            "completion_rate": 0.0,
        }
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT status, COUNT(*) FROM bookings GROUP BY status")
                for status, count in cur.fetchall():
                    metrics["total_bookings"] += count
                    if status == "completed":
                        metrics["completed_bookings"] = count
                    elif status == "in-progress":
                        metrics["in_progress_bookings"] = count
                    elif status == "unassigned":
                        metrics["unassigned_bookings"] = count
                cur.execute("SELECT COUNT(*) FROM drivers")
                metrics["total_drivers"] = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM users")
                metrics["total_users"] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            pass

        if metrics["total_bookings"]:
            metrics["completion_rate"] = round(
                metrics["completed_bookings"] / metrics["total_bookings"] * 100, 2
            )
        return metrics
