import json
import urllib.request
import urllib.parse
from datetime import datetime

from models import db, Booking, RoutePlan
from tz_util import now_local, now_iso


class RouteOptimizer:
    OSRM_BASE = 'https://router.project-osrm.org'
    NOMINATIM_BASE = 'https://nominatim.openstreetmap.org'
    USER_AGENT = 'TFA-Shuttles-RouteOptimizer/1.0'
    AVG_SPEED_KMH = 35.0

    def __init__(self, coords=None):
        self.coords = coords or {}

    # ---------- public ----------

    def get_overview(self):
        total = RoutePlan.query.count()
        latest = RoutePlan.query.order_by(RoutePlan.id.desc()).first()
        return {
            'total_routes': total,
            'optimized_routes': total,
            'fuel_savings': 0,
            'total_distance': round(latest.total_distance_km, 1) if latest else 0,
            'time_savings': 0,
            'optimization_rate': 100 if total else 0,
        }

    def get_recent_plans(self, limit=10):
        rows = RoutePlan.query.order_by(RoutePlan.id.desc()).limit(limit).all()
        return [self._plan_to_dict(r) for r in rows]

    def get_bookings_for_date(self, plan_date):
        """Loose date match — accepts 2026-09-14 or 2026-09-14T18:00."""
        all_bookings = Booking.query.all()
        matched = []
        for b in all_bookings:
            if not b.date_time:
                continue
            if b.date_time[:10] == plan_date or plan_date in b.date_time:
                matched.append(b)
        return matched

    def plan_from_booking_ids(self, plan_date, booking_ids, driver_id=''):
        """Plan a route from an explicit list of booking IDs."""
        bookings = Booking.query.filter(Booking.id.in_(booking_ids)).all()
        if not bookings:
            return None

        # Resolve missing coords
        for b in bookings:
            if b.pickup_lat is None or b.pickup_lng is None:
                c = self._resolve_coords(b.pickup)
                if c:
                    b.pickup_lat, b.pickup_lng = c
            if b.dropoff_lat is None or b.dropoff_lng is None:
                c = self._resolve_coords(b.dropoff)
                if c:
                    b.dropoff_lat, b.dropoff_lng = c
        db.session.commit()

        stops = self._stops_from_bookings(bookings)
        skipped = []
        for b in bookings:
            if b.pickup_lat is None or b.dropoff_lat is None:
                skipped.append({
                    'booking_id': b.id,
                    'user_id': b.user_id,
                    'pickup': b.pickup,
                    'dropoff': b.dropoff,
                    'reason': 'missing coordinates',
                })

        if not stops:
            return None

        ordered = self._solve_nearest_neighbor(stops)
        km, mins = self._route_distance(ordered)

        plan = RoutePlan(
            plan_date=plan_date,
            driver_id=driver_id or '',
            stops_json=json.dumps({
                'driver_groups': [{
                    'driver_id': driver_id or 'unassigned',
                    'stops': ordered,
                    'distance_km': km,
                    'time_min': mins,
                }],
                'skipped': skipped,
            }),
            total_distance_km=km,
            total_time_min=mins,
            created_at=datetime.now().isoformat(),
        )
        db.session.add(plan)
        db.session.commit()
        return self._plan_to_dict(plan)

    def plan_for_date(self, plan_date):
        bookings = self.get_bookings_for_date(plan_date)
        if not bookings:
            return None

        # Fill in missing coordinates
        for b in bookings:
            if b.pickup_lat is None or b.pickup_lng is None:
                c = self._resolve_coords(b.pickup)
                if c:
                    b.pickup_lat, b.pickup_lng = c
            if b.dropoff_lat is None or b.dropoff_lng is None:
                c = self._resolve_coords(b.dropoff)
                if c:
                    b.dropoff_lat, b.dropoff_lng = c
        db.session.commit()

        # Group by driver
        groups = {}
        for b in bookings:
            groups.setdefault(b.driver_id or 'unassigned', []).append(b)

        driver_groups = []
        grand_km = 0.0
        grand_min = 0.0
        skipped = []

        for driver_id, group in groups.items():
            stops = self._stops_from_bookings(group)
            for b in group:
                if b.pickup_lat is None or b.dropoff_lat is None:
                    skipped.append({
                        'booking_id': b.id,
                        'user_id': b.user_id,
                        'pickup': b.pickup,
                        'dropoff': b.dropoff,
                        'reason': 'missing coordinates',
                    })
            if not stops:
                continue
            ordered = self._solve_nearest_neighbor(stops)
            km, mins = self._route_distance(ordered)
            grand_km += km
            grand_min += mins
            driver_groups.append({
                'driver_id': driver_id,
                'stops': ordered,
                'distance_km': km,
                'time_min': mins,
            })

        plan = RoutePlan(
            plan_date=plan_date,
            driver_id='',
            stops_json=json.dumps({
                'driver_groups': driver_groups,
                'skipped': skipped,
            }),
            total_distance_km=grand_km,
            total_time_min=grand_min,
            created_at=now_iso(),
        )
        db.session.add(plan)
        db.session.commit()
        return self._plan_to_dict(plan)

    # ---------- internals ----------

    def _plan_to_dict(self, row):
        raw = json.loads(row.stops_json or '{}')
        # Backward compatibility with old flat-list plans
        if isinstance(raw, list):
            driver_groups = [{'driver_id': row.driver_id or 'all', 'stops': raw,
                              'distance_km': row.total_distance_km,
                              'time_min': row.total_time_min}]
            skipped = []
        else:
            driver_groups = raw.get('driver_groups', [])
            skipped = raw.get('skipped', [])
        return {
            'id': row.id,
            'plan_date': row.plan_date,
            'driver_groups': driver_groups,
            'skipped': skipped,
            'total_distance_km': row.total_distance_km,
            'total_time_min': row.total_time_min,
            'created_at': row.created_at,
        }

    def _resolve_coords(self, location_name):
        if not location_name:
            return None
        if location_name in self.coords:
            return self.coords[location_name]
        lower = location_name.strip().lower()
        for key, val in self.coords.items():
            if key.lower() == lower:
                return val
        # Nominatim
        try:
            q = urllib.parse.urlencode({'q': location_name, 'format': 'json', 'limit': 1})
            url = f'{self.NOMINATIM_BASE}/search?{q}'
            req = urllib.request.Request(url, headers={'User-Agent': self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            if data:
                return (float(data[0]['lat']), float(data[0]['lon']))
        except Exception as e:
            print(f"Geocode failed for '{location_name}': {e}")
        return None

    def _stops_from_bookings(self, bookings):
        stops = []
        for b in bookings:
            if b.pickup_lat is None or b.dropoff_lat is None:
                continue
            stops.append({
                'booking_id': b.id,
                'user_id': b.user_id,
                'pickup': b.pickup,
                'dropoff': b.dropoff,
                'pickup_latlng': [b.pickup_lat, b.pickup_lng],
                'dropoff_latlng': [b.dropoff_lat, b.dropoff_lng],
                'date_time': b.date_time,
                'status': b.status,
            })
        return stops

    def _solve_nearest_neighbor(self, stops):
        if not stops:
            return []
        remaining = list(stops)
        ordered = []
        current = remaining[0]['pickup_latlng']
        while remaining:
            best_i = 0
            best_d = float('inf')
            for i, s in enumerate(remaining):
                d = self._haversine_km(current, s['pickup_latlng'])
                if d < best_d:
                    best_d = d
                    best_i = i
            chosen = remaining.pop(best_i)
            ordered.append(chosen)
            current = chosen['dropoff_latlng']
        return ordered

    def _route_distance(self, ordered_stops):
        if not ordered_stops:
            return 0.0, 0.0
        points = []
        for s in ordered_stops:
            points.append(tuple(s['pickup_latlng']))
            points.append(tuple(s['dropoff_latlng']))
        try:
            coord_str = ';'.join(f'{lng},{lat}' for lat, lng in points)
            url = f'{self.OSRM_BASE}/route/v1/driving/{coord_str}?overview=false'
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            if data.get('code') == 'Ok' and data.get('routes'):
                r = data['routes'][0]
                return round(r['distance'] / 1000.0, 2), round(r['duration'] / 60.0, 1)
        except Exception as e:
            print(f"OSRM failed: {e}")
        total = sum(self._haversine_km(points[i], points[i+1]) for i in range(len(points)-1))
        return round(total, 2), round(total / self.AVG_SPEED_KMH * 60, 1)

    @staticmethod
    def _haversine_km(a, b):
        import math
        R = 6371.0
        lat1, lng1 = math.radians(a[0]), math.radians(a[1])
        lat2, lng2 = math.radians(b[0]), math.radians(b[1])
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
        return 2 * R * math.asin(math.sqrt(h))
