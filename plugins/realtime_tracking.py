from datetime import datetime


class RealTimeTracker:
    def __init__(self):
        # In-memory positions: {driver_id: {"lat": ..., "lng": ..., "ts": ...}}
        self.positions = {}

    def update_position(self, driver_id, lat, lng):
        self.positions[driver_id] = {
            "lat": lat,
            "lng": lng,
            "ts": datetime.now().isoformat()
        }

    def get_position(self, driver_id):
        return self.positions.get(driver_id)

    def get_all_positions(self):
        return dict(self.positions)

    def get_overview(self):
        active = len(self.positions)
        return {
            "total_vehicles": active,
            "active_vehicles": active,
            "idle_vehicles": 0,
            "avg_speed": 0,
            "on_time_rate": 0,
            "delivery_completion": 0
        }
