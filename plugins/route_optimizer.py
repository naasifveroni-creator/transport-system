import json
import urllib.request
import urllib.parse
from datetime import datetime

from models import db, RoutePlan, Booking


class RouteOptimizer:
    OSRM_BASE = 'https://router.project-osrm.org'
    AVG_SPEED_KMH = 35.0  # fallback when OSRM time unavailable

    def __init__(self, coords=None):
        # coords: {location_name: (lat, lng)}
        self.coords = coords or {}

    # ---------- public API ----------

    def get_overview(self):
        total = RoutePlan.query.count()
        latest = RoutePlan.query.order_by(RoutePlan.id.desc()).first()
        return {
            'total_routes': total,
            'optimized_routes': total,
            'fuel_savings': round(latest.total_distance_km * 0.15, 1) if latest else 0,
            'total_distance': round(latest.total_distance_km, 1) if latest else 0,
            'time_savings': 0,
            'optimization_rate': 100 if total else 0,
        }

    def get_recent_plans(self, limit=20):
        rows = RoutePlan.query.order_by(RoutePlan.id.desc()).limit(limit).all()
        return [self._plan_to_dict(r) for r in rows]

    def plan_for_date(self, plan_date, driver_id=''):
        """
        Take all unassigned bookings for a date, optimize order, save plan.
        Returns the plan dict.
        """
        # Fetch bookings for that date
        bookings = Booking.query.all()
        stops = []
        for b in bookings:
            if not b.date_time or not b.date_time.startswith(plan_date):
                continue

            # Prefer per-booking coordinates; fall back to LOCATION_COORDS lookup
            p_lat, p_lng = b.pickup_lat, b.pickup_lng
            d_lat, d_lng = b.dropoff_lat, b.dropoff_lng

            if (p_lat is None or p_lng is None) and b.pickup in self.coords:
                p_lat, p_lng = self.coords[b.pickup]
            if (d_lat is None or d_lng is None) and b.dropoff in self.coords:
                d_lat, d_lng = self.coords[b.dropoff]

            if p_lat is None or p_lng is None or d_lat is None or d_lng is None:
                # Can't route this one — skip
                continue

            stops.append({
                'booking_id': b.id,
                'user_id': b.user_id,
                'pickup': b.pickup,
                'dropoff': b.dropoff,
                'pickup_latlng': [p_lat, p_lng],
                'dropoff_latlng': [d_lat, d_lng],
            })

        if not stops:
            return None

        ordered = self._solve_nearest_neighbor(stops)
        distance_km, time_min = self._total_route_distance(ordered)

        plan = RoutePlan(
            plan_date=plan_date,
            driver_id=driver_id or '',
            stops_json=json.dumps(ordered),
            total_distance_km=distance_km,
            total_time_min=time_min,
            created_at=datetime.now().isoformat(),
        )
        db.session.add(plan)
        db.session.commit()
        return self._plan_to_dict(plan)

    # ---------- internals ----------

    def _plan_to_dict(self, row):
        return {
            'id': row.id,
            'plan_date': row.plan_date,
            'driver_id': row.driver_id,
            'stops': json.loads(row.stops_json or '[]'),
            'total_distance_km': row.total_distance_km,
            'total_time_min': row.total_time_min,
            'created_at': row.created_at,
        }

    def _solve_nearest_neighbor(self, stops):
        """
        Greedy nearest-neighbor ordering.
        Start from the first stop's pickup, always go to the closest remaining stop.
        """
        if not stops:
            return []
        remaining = list(stops)
        ordered = []
        current = remaining[0]['pickup_latlng']
        while remaining:
            nearest_idx = 0
            nearest_dist = float('inf')
            for i, s in enumerate(remaining):
                d = self._haversine_km(current, s['pickup_latlng'])
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_idx = i
            chosen = remaining.pop(nearest_idx)
            ordered.append(chosen)
            current = chosen['dropoff_latlng']
        return ordered

    def _total_route_distance(self, ordered_stops):
        """Use OSRM for real road distances between consecutive stops."""
        if not ordered_stops:
            return 0.0, 0.0

        # Build waypoint list: pickup then dropoff for each stop
        points = []
        for s in ordered_stops:
            points.append(tuple(s['pickup_latlng']))
            points.append(tuple(s['dropoff_latlng']))

        # Try OSRM route API for the whole polyline
        try:
            coords_str = ';'.join(f'{lng},{lat}' for lat, lng in points)
            url = f'{self.OSRM_BASE}/route/v1/driving/{coords_str}?overview=false'
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            if data.get('code') == 'Ok' and data.get('routes'):
                route = data['routes'][0]
                distance_km = route['distance'] / 1000.0
                time_min = route['duration'] / 60.0
                return round(distance_km, 2), round(time_min, 1)
        except Exception as e:
            print(f"OSRM failed: {e}")

        # Fallback: straight-line distance
        total_km = 0.0
        for i in range(len(points) - 1):
            total_km += self._haversine_km(points[i], points[i + 1])
        time_min = (total_km / self.AVG_SPEED_KMH) * 60.0
        return round(total_km, 2), round(time_min, 1)

    @staticmethod
    def _haversine_km(a, b):
        import math
        R = 6371.0
        lat1, lng1 = math.radians(a[0]), math.radians(a[1])
        lat2, lng2 = math.radians(b[0]), math.radians(b[1])
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        h = (math.sin(dlat/2)**2 +
             math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2)
        return 2 * R * math.asin(math.sqrt(h))
