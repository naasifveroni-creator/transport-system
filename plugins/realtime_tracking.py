from datetime import datetime, timedelta
from models import db, DriverPosition
from tz_util import now_local, now_iso


class RealTimeTracker:
    """
    DB-backed driver position tracker.
    Positions are stored in Postgres so they survive app restarts.
    """

    ACTIVE_WINDOW_SECONDS = 300  # 5 minutes = considered "active"

    def __init__(self):
        pass

    def update_position(self, driver_id, lat, lng, speed=0, heading=0, route=''):
        pos = DriverPosition(
            driver_id=driver_id,
            lat=float(lat),
            lng=float(lng),
            speed=float(speed or 0),
            heading=float(heading or 0),
            route=route or '',
            recorded_at=now_iso(),
        )
        db.session.add(pos)
        db.session.commit()
        return pos

    def get_latest_position(self, driver_id):
        return (DriverPosition.query
                .filter_by(driver_id=driver_id)
                .order_by(DriverPosition.id.desc())
                .first())

    def get_all_latest_positions(self):
        """One latest position per driver."""
        rows = (DriverPosition.query
                .order_by(DriverPosition.id.desc())
                .all())
        seen = {}
        for r in rows:
            if r.driver_id not in seen:
                seen[r.driver_id] = r
        return {did: pos.to_dict() for did, pos in seen.items()}

    def get_track(self, driver_id, minutes=60):
        """Ordered positions for one driver within the last N minutes."""
        cutoff = (now_local() - timedelta(minutes=minutes)).isoformat()
        rows = (DriverPosition.query
                .filter(DriverPosition.driver_id == driver_id)
                .filter(DriverPosition.recorded_at >= cutoff)
                .order_by(DriverPosition.id.asc())
                .all())
        return [r.to_dict() for r in rows]

    def clear(self):
        DriverPosition.query.delete()
        db.session.commit()

    def get_overview(self):
        latest = self.get_all_latest_positions()
        now = now_local()

        active = 0
        idle = 0
        total_speed = 0.0

        for pos in latest.values():
            try:
                ts = datetime.fromisoformat(pos['recorded_at'])
                age = (now - ts).total_seconds()
            except Exception:
                age = 99999

            if age < self.ACTIVE_WINDOW_SECONDS:
                active += 1
                total_speed += pos.get('speed', 0)
            else:
                idle += 1

        avg_speed = (total_speed / active) if active else 0

        return {
            'total_vehicles': len(latest),
            'active_vehicles': active,
            'idle_vehicles': idle,
            'avg_speed': round(avg_speed, 1),
            'on_time_rate': 0,
            'delivery_completion': 0,
        }
