from models import Booking, Driver, DBUser as User


class BusinessAnalytics:
    def __init__(self, db_path=None):
        pass

    def get_dashboard_metrics(self):
        total_bookings = Booking.query.count()
        completed = Booking.query.filter_by(status='completed').count()
        in_progress = Booking.query.filter_by(status='in-progress').count()
        unassigned = Booking.query.filter_by(status='unassigned').count()
        total_drivers = Driver.query.count()
        total_users = User.query.count()

        completion_rate = 0.0
        if total_bookings:
            completion_rate = round(completed / total_bookings * 100, 2)

        return {
            "total_bookings": total_bookings,
            "completed_bookings": completed,
            "in_progress_bookings": in_progress,
            "unassigned_bookings": unassigned,
            "total_drivers": total_drivers,
            "total_users": total_users,
            "completion_rate": completion_rate,
        }
