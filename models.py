from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    username = db.Column(db.String(80), primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_driver = db.Column(db.Boolean, default=False, nullable=False)
    registered_address = db.Column(db.String(255), default='')
    travel_allowance = db.Column(db.Float, default=0.0)

    penalties = db.relationship('Penalty', backref='user', lazy=True,
                                cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'username': self.username,
            'name': self.name,
            'password': self.password,
            'is_admin': self.is_admin,
            'is_driver': self.is_driver,
            'registered_address': self.registered_address or '',
            'travel_allowance': self.travel_allowance or 0.0,
            'penalties': [p.to_dict() for p in self.penalties],
        }


class Penalty(db.Model):
    __tablename__ = 'penalties'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), db.ForeignKey('users.username'),
                         nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255), default='')
    timestamp = db.Column(db.String(64), default='')

    def to_dict(self):
        return {
            'amount': self.amount,
            'reason': self.reason,
            'timestamp': self.timestamp,
        }


class Driver(db.Model):
    __tablename__ = 'drivers'

    username = db.Column(db.String(80), primary_key=True)
    first_name = db.Column(db.String(80), default='')
    last_name = db.Column(db.String(80), default='')
    license_plate = db.Column(db.String(40), default='')


class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(80), nullable=False)
    driver_id = db.Column(db.String(80), default='unassigned')
    date_time = db.Column(db.String(64), default='')
    pickup = db.Column(db.String(120), default='')
    dropoff = db.Column(db.String(120), default='')
    status = db.Column(db.String(32), default='unassigned')
    trip_start_time = db.Column(db.String(64), nullable=True)
    trip_end_time = db.Column(db.String(64), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'driver_id': self.driver_id,
            'date_time': self.date_time,
            'pickup': self.pickup,
            'dropoff': self.dropoff,
            'status': self.status,
            'trip_start_time': self.trip_start_time,
            'trip_end_time': self.trip_end_time,
        }


class Waybill(db.Model):
    __tablename__ = 'waybills'

    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.String(80), nullable=False)
    date = db.Column(db.String(40), default='')
    time = db.Column(db.String(40), default='')
    pickup = db.Column(db.String(120), default='')
    dropoff = db.Column(db.String(120), default='')
    cost = db.Column(db.Float, default=0.0)
    route = db.Column(db.String(255), default='')


class TripHistory(db.Model):
    __tablename__ = 'trip_history'

    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.String(80), nullable=False)
    date = db.Column(db.String(40), default='')
    time = db.Column(db.String(40), default='')
    pickup = db.Column(db.String(120), default='')
    dropoff = db.Column(db.String(120), default='')
    cost = db.Column(db.Float, default=0.0)
    route = db.Column(db.String(255), default='')


class GlobalTimeSlot(db.Model):
    __tablename__ = 'global_time_slots'

    id = db.Column(db.Integer, primary_key=True)
    slot = db.Column(db.String(40), unique=True, nullable=False)
    enabled = db.Column(db.Boolean, default=True)


class CampaignTimeSlot(db.Model):
    __tablename__ = 'campaign_time_slots'

    id = db.Column(db.Integer, primary_key=True)
    campaign = db.Column(db.String(80), nullable=False)
    slot = db.Column(db.String(40), nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint('campaign', 'slot', name='uq_campaign_slot'),)


# Alias to avoid conflict with flask_login.UserMixin in app.py
DBUser = User
