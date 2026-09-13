from datetime import datetime, timedelta
from collections import defaultdict

from models import (
    db, Booking, Driver, DBUser as User, Penalty,
    Invoice, TripHistory, DriverPosition
)


class BusinessAnalytics:
    """
    Real analytics engine over the app's transactional data.
    All methods take optional start/end ISO dates.
    """

    # ---------- KPI OVERVIEW ----------

    def get_overview_metrics(self, start=None, end=None):
        """Headline KPIs for a period, with % change vs the previous equal-length period."""
        bookings = self._bookings_in_range(start, end)
        invoices = self._invoices_in_range(start, end)

        total_bookings = len(bookings)
        completed = sum(1 for b in bookings if b.status == 'completed')
        cancelled = sum(1 for b in bookings if b.status == 'cancelled')
        in_progress = sum(1 for b in bookings if b.status == 'in-progress')
        unassigned = sum(1 for b in bookings if b.status == 'unassigned')

        total_revenue = sum(i.amount for i in invoices if i.status == 'paid')
        pending_revenue = sum(i.amount for i in invoices if i.status == 'pending')

        completion_rate = round(completed / total_bookings * 100, 1) if total_bookings else 0
        avg_trip_value = round(total_revenue / completed, 2) if completed else 0

        # Previous-period comparison
        prev_start, prev_end = self._previous_period(start, end)
        prev_bookings = self._bookings_in_range(prev_start, prev_end)
        prev_invoices = self._invoices_in_range(prev_start, prev_end)
        prev_completed = sum(1 for b in prev_bookings if b.status == 'completed')
        prev_revenue = sum(i.amount for i in prev_invoices if i.status == 'paid')

        return {
            'total_bookings': total_bookings,
            'completed': completed,
            'cancelled': cancelled,
            'in_progress': in_progress,
            'unassigned': unassigned,
            'completion_rate': completion_rate,
            'total_revenue': round(total_revenue, 2),
            'pending_revenue': round(pending_revenue, 2),
            'avg_trip_value': avg_trip_value,
            'bookings_change': self._pct_change(total_bookings, len(prev_bookings)),
            'completed_change': self._pct_change(completed, prev_completed),
            'revenue_change': self._pct_change(total_revenue, prev_revenue),
            'period_start': start or 'all-time',
            'period_end': end or 'now',
        }

    # ---------- CHARTS ----------

    def get_revenue_trend(self, days=30):
        """Daily paid revenue for the last N days."""
        today = datetime.now().date()
        series = {}
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            series[d.isoformat()] = 0.0

        start = (today - timedelta(days=days - 1)).isoformat()
        invoices = Invoice.query.filter(
            Invoice.status == 'paid',
            Invoice.paid_at.isnot(None),
            Invoice.paid_at >= start,
        ).all()

        for inv in invoices:
            key = (inv.paid_at or '')[:10]
            if key in series:
                series[key] += inv.amount or 0

        return {
            'labels': list(series.keys()),
            'data': [round(v, 2) for v in series.values()],
        }

    def get_bookings_trend(self, days=30):
        """Daily new bookings for the last N days."""
        today = datetime.now().date()
        series = {}
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            series[d.isoformat()] = 0

        start = (today - timedelta(days=days - 1)).isoformat()
        bookings = Booking.query.filter(Booking.date_time >= start).all()
        for b in bookings:
            key = (b.date_time or '')[:10]
            if key in series:
                series[key] += 1

        return {
            'labels': list(series.keys()),
            'data': list(series.values()),
        }

    def get_status_breakdown(self, start=None, end=None):
        """Booking statuses as a pie chart."""
        bookings = self._bookings_in_range(start, end)
        counts = defaultdict(int)
        for b in bookings:
            counts[b.status or 'unassigned'] += 1
        return {
            'labels': list(counts.keys()),
            'data': list(counts.values()),
        }

    def get_hourly_distribution(self, start=None, end=None):
        """Bookings by hour of day (0–23)."""
        bookings = self._bookings_in_range(start, end)
        hours = [0] * 24
        for b in bookings:
            try:
                # date_time looks like '2026-09-14T18:00' or '2026-09-14 18:00'
                s = (b.date_time or '').replace('T', ' ')
                if ' ' in s:
                    h = int(s.split(' ')[1][:2])
                    if 0 <= h < 24:
                        hours[h] += 1
            except Exception:
                pass
        return {
            'labels': [f'{h:02d}:00' for h in range(24)],
            'data': hours,
        }

    def get_weekday_distribution(self, start=None, end=None):
        """Bookings by weekday (Mon–Sun)."""
        bookings = self._bookings_in_range(start, end)
        counts = [0] * 7
        for b in bookings:
            try:
                dt = datetime.fromisoformat((b.date_time or '').replace('T', ' '))
                counts[dt.weekday()] += 1
            except Exception:
                pass
        return {
            'labels': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            'data': counts,
        }

    def get_top_routes(self, limit=8, start=None, end=None):
        """Most-booked pickup→dropoff pairs."""
        bookings = self._bookings_in_range(start, end)
        counts = defaultdict(int)
        for b in bookings:
            key = f"{b.pickup} → {b.dropoff}"
            counts[key] += 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:limit]
        return {
            'labels': [k for k, _ in top],
            'data': [v for _, v in top],
        }

    def get_top_drivers(self, limit=5, start=None, end=None):
        """Drivers ranked by completed trips and revenue."""
        bookings = self._bookings_in_range(start, end)
        stats = defaultdict(lambda: {'trips': 0, 'revenue': 0.0})
        for b in bookings:
            if b.status == 'completed' and b.driver_id and b.driver_id != 'unassigned':
                stats[b.driver_id]['trips'] += 1

        invoices = self._invoices_in_range(start, end)
        for inv in invoices:
            if inv.status == 'paid' and inv.driver_id:
                stats[inv.driver_id]['revenue'] += inv.amount or 0

        ranked = sorted(stats.items(), key=lambda x: (-x[1]['trips'], -x[1]['revenue']))[:limit]
        return [
            {'driver_id': d, 'trips': s['trips'], 'revenue': round(s['revenue'], 2)}
            for d, s in ranked
        ]

    def get_top_users(self, limit=5, start=None, end=None):
        """Most active users by booking count."""
        bookings = self._bookings_in_range(start, end)
        counts = defaultdict(int)
        for b in bookings:
            counts[b.user_id] += 1
        ranked = sorted(counts.items(), key=lambda x: -x[1])[:limit]
        return [{'user_id': u, 'bookings': c} for u, c in ranked]

    # ---------- INSIGHTS ----------

    def get_insights(self, start=None, end=None):
        """Auto-generated plain-English insights."""
        insights = []

        # Peak hour
        hours = self.get_hourly_distribution(start, end)
        if any(hours['data']):
            peak_idx = hours['data'].index(max(hours['data']))
            insights.append({
                'icon': 'clock',
                'label': 'Peak booking hour',
                'value': hours['labels'][peak_idx],
                'detail': f"{hours['data'][peak_idx]} bookings in this hour",
            })

        # Busiest day
        wd = self.get_weekday_distribution(start, end)
        if any(wd['data']):
            peak_idx = wd['data'].index(max(wd['data']))
            insights.append({
                'icon': 'calendar',
                'label': 'Busiest day',
                'value': wd['labels'][peak_idx],
                'detail': f"{wd['data'][peak_idx]} bookings",
            })

        # Top route
        routes = self.get_top_routes(limit=1, start=start, end=end)
        if routes['labels']:
            insights.append({
                'icon': 'route',
                'label': 'Top route',
                'value': routes['labels'][0],
                'detail': f"{routes['data'][0]} bookings",
            })

        # Top driver
        drivers = self.get_top_drivers(limit=1, start=start, end=end)
        if drivers:
            insights.append({
                'icon': 'driver',
                'label': 'Top driver',
                'value': drivers[0]['driver_id'],
                'detail': f"{drivers[0]['trips']} trips · R {drivers[0]['revenue']:.2f}",
            })

        # Revenue at risk (pending invoices)
        pending_total = db.session.query(db.func.sum(Invoice.amount)).filter(
            Invoice.status == 'pending'
        ).scalar() or 0
        pending_count = Invoice.query.filter_by(status='pending').count()
        if pending_count:
            insights.append({
                'icon': 'money',
                'label': 'Revenue pending',
                'value': f"R {pending_total:.2f}",
                'detail': f"{pending_count} unpaid invoices",
            })

        # Completion rate warning
        overview = self.get_overview_metrics(start, end)
        if overview['total_bookings'] > 5 and overview['completion_rate'] < 50:
            insights.append({
                'icon': 'warning',
                'label': 'Low completion rate',
                'value': f"{overview['completion_rate']}%",
                'detail': f"{overview['unassigned']} unassigned bookings need attention",
            })

        # Active drivers this period
        active = self._active_drivers(start, end)
        insights.append({
            'icon': 'driver',
            'label': 'Active drivers',
            'value': str(active),
            'detail': f'out of {Driver.query.count()} registered',
        })

        return insights

    # ---------- REPORT DATA ----------

    def get_report(self, start=None, end=None, driver_id=None, status=None):
        """Filterable booking report joined with invoice info."""
        q = Booking.query
        if start:
            q = q.filter(Booking.date_time >= start)
        if end:
            q = q.filter(Booking.date_time <= end)
        if driver_id:
            q = q.filter(Booking.driver_id == driver_id)
        if status:
            q = q.filter(Booking.status == status)

        bookings = q.order_by(Booking.date_time.desc()).all()
        booking_ids = [b.id for b in bookings]
        invoices = {i.booking_id: i for i in Invoice.query.filter(
            Invoice.booking_id.in_(booking_ids)
        ).all()} if booking_ids else {}

        rows = []
        for b in bookings:
            inv = invoices.get(b.id)
            rows.append({
                'id': b.id,
                'date_time': b.date_time,
                'user_id': b.user_id,
                'driver_id': b.driver_id or '—',
                'pickup': b.pickup,
                'dropoff': b.dropoff,
                'status': b.status,
                'invoice_status': inv.status if inv else '—',
                'invoice_amount': round(inv.amount, 2) if inv else 0.0,
            })

        total_trips = len(rows)
        total_invoiced = round(sum(r['invoice_amount'] for r in rows), 2)
        total_paid = round(sum(r['invoice_amount'] for r in rows
                              if r['invoice_status'] == 'paid'), 2)

        return {
            'rows': rows,
            'summary': {
                'total_trips': total_trips,
                'total_invoiced': total_invoiced,
                'total_paid': total_paid,
                'total_pending': round(total_invoiced - total_paid, 2),
            },
        }

    # ---------- HELPERS ----------

    def _bookings_in_range(self, start, end):
        q = Booking.query
        if start:
            q = q.filter(Booking.date_time >= start)
        if end:
            q = q.filter(Booking.date_time <= end + 'T23:59:59')
        return q.all()

    def _invoices_in_range(self, start, end):
        q = Invoice.query
        if start:
            q = q.filter(Invoice.created_at >= start)
        if end:
            q = q.filter(Invoice.created_at <= end + 'T23:59:59')
        return q.all()

    def _active_drivers(self, start, end):
        q = Booking.query.filter(
            Booking.status == 'completed',
            Booking.driver_id.isnot(None),
            Booking.driver_id != 'unassigned',
        )
        if start:
            q = q.filter(Booking.date_time >= start)
        if end:
            q = q.filter(Booking.date_time <= end + 'T23:59:59')
        return len(set(b.driver_id for b in q.all()))

    def _previous_period(self, start, end):
        """Compute the equivalent previous window."""
        if not start or not end:
            return None, None
        try:
            s = datetime.fromisoformat(start)
            e = datetime.fromisoformat(end)
            length = (e - s).days or 1
            prev_end = s - timedelta(days=1)
            prev_start = prev_end - timedelta(days=length)
            return prev_start.isoformat()[:10], prev_end.isoformat()[:10]
        except Exception:
            return None, None

    @staticmethod
    def _pct_change(current, previous):
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round((current - previous) / previous * 100, 1)
