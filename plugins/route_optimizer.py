from models import Booking


class RouteOptimizer:
    def __init__(self, db_path=None):
        pass

    def get_overview(self):
        total_routes = Booking.query.count()
        return {
            "total_routes": total_routes,
            "optimized_routes": 0,
            "fuel_savings": 0,
            "total_distance": 0,
            "time_savings": 0,
            "optimization_rate": 0,
        }

    def optimize(self, bookings):
        return sorted(
            bookings,
            key=lambda b: (b.get("pickup", ""), b.get("dropoff", ""))
        )
