from plugins.time_slot_manager import TimeSlotManager
from plugins.booking_enhancements import get_available_time_slots, validate_booking_time
from plugins.business_analytics import BusinessAnalytics
from plugins.user_manager import UserManager
from plugins.admin_enhancements import AdminUserManager
from plugins.route_optimizer import RouteOptimizer
from plugins.realtime_tracking import RealTimeTracker
from plugins.campaign_registration import CampaignBulkRegistration
from plugins.billing_mis import BillingMIS

import json
import csv
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from flask_login import login_required, LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import io
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-key")

# ---- Database setup ----
from models import db, User as DBUser, Penalty, Driver, Booking, Waybill, TripHistory, GlobalTimeSlot, CampaignTimeSlot, Invoice, DriverPosition, RoutePlan

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    import os as _os
    _base = _os.path.abspath(_os.path.dirname(__file__))
    database_url = f"sqlite:///{_base}/instance/local_dev.db"
if not database_url:
    import os as _os
    _base = _os.path.abspath(_os.path.dirname(__file__))
    database_url = f"sqlite:///{_base}/instance/local_dev.db"
# Render gives postgres:// but SQLAlchemy wants postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db.init_app(app)

with app.app_context():
    db.create_all()


# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


# User class for Flask-Login
class User(UserMixin):
    def __init__(self, username, is_admin=False, is_driver=False):
        self.username = username
        self.is_admin = is_admin
        self.is_driver = is_driver

    def get_id(self):
        return self.username


# User loader function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    data = load_data()
    user_data = data.get('users', {}).get(user_id)
    if user_data:
        return User(
            user_data['username'],
            user_data.get('is_admin', False),
            user_data.get('is_driver', False)
        )
    return None


# List of valid locations and time slots
# Approximate coordinates for each pickup/dropoff location.
# Adjust these to your real spots.
LOCATION_COORDS = {
    'Blvd':         (-26.2041, 28.0473),
    'Match Factory': (-26.2018, 28.0421),
    'Adderly':      (-26.2055, 28.0438),
    'Wembly Sqr':   (-26.2088, 28.0405),
    'Campus A':     (-26.1900, 28.0300),
    'Campus B':     (-26.1850, 28.0380),
    'Campus C':     (-26.1970, 28.0550),
    'Downtown':     (-26.2041, 28.0473),
    'Airport':      (-26.1391, 28.2460),
    'Train Station': (-26.2030, 28.0450),
}

LOCATIONS = ['Blvd', 'Match Factory', 'Adderly', 'Wembly Sqr', 'Campus A', 'Campus B', 'Campus C', 'Downtown', 'Airport', 'Train Station']
TIME_SLOTS = ['6pm', '7pm', '8pm', '9pm', '10pm', '11pm', '12pm', '12am', '1am', '2am', '3am', '4am', '5am', '6am']


def load_data():
    """Return the whole store as a dict, backed by Postgres."""
    users = {}
    for u in DBUser.query.all():
        users[u.username] = u.to_dict()

    drivers = {}
    for d in Driver.query.all():
        drivers[d.username] = {
            'first_name': d.first_name,
            'last_name': d.last_name,
            'license_plate': d.license_plate,
            'waybills': [
                {
                    'Date': w.date, 'Time': w.time,
                    'Pickup': w.pickup, 'Dropoff': w.dropoff,
                    'Cost': w.cost, 'Route': w.route,
                    'Driver_ID': w.driver_id,
                }
                for w in Waybill.query.filter_by(driver_id=d.username).all()
            ],
            'trip_history': [
                {
                    'date': t.date, 'time': t.time,
                    'pickup': t.pickup, 'dropoff': t.dropoff,
                    'cost': t.cost, 'route': t.route,
                }
                for t in TripHistory.query.filter_by(driver_id=d.username).all()
            ],
        }

    bookings = []
    for b in Booking.query.all():
        bookings.append(b.to_dict())

    # Seed admin if no users exist
    if not users:
        from werkzeug.security import generate_password_hash as _gh
        admin_pw = os.environ.get("ADMIN_PASSWORD", "changeme")
        admin = DBUser(
            username='admin',
            name='Admin User',
            password=_gh(admin_pw),
            is_admin=True,
            is_driver=False,
            registered_address='Admin Headquarters',
            registered_lat=None,
            registered_lng=None,
            travel_allowance=0.0,
        )
        db.session.add(admin)
        db.session.commit()
        users['admin'] = admin.to_dict()

    return {
        'users': users,
        'bookings': bookings,
        'drivers': drivers,
        'driver_bookings': {},
    }

def save_data(data):
    """Persist the given dict back to Postgres."""
    # ---- Users + penalties ----
    for username, u in data.get('users', {}).items():
        existing = DBUser.query.get(username)
        if not existing:
            existing = DBUser(username=username)
            db.session.add(existing)
        existing.name = u.get('name', username)
        existing.password = u.get('password', '')
        existing.is_admin = bool(u.get('is_admin', False))
        existing.is_driver = bool(u.get('is_driver', False))
        existing.registered_address = u.get('registered_address', '')
        existing.registered_lat = u.get('registered_lat')
        existing.registered_lng = u.get('registered_lng')
        existing.travel_allowance = float(u.get('travel_allowance', 0) or 0)

        Penalty.query.filter_by(username=username).delete()
        for p in u.get('penalties', []):
            db.session.add(Penalty(
                username=username,
                amount=float(p.get('amount', 0)),
                reason=p.get('reason', ''),
                timestamp=p.get('timestamp', ''),
            ))

    # ---- Drivers ----
    for username, d in data.get('drivers', {}).items():
        existing = Driver.query.get(username)
        if not existing:
            existing = Driver(username=username)
            db.session.add(existing)
        existing.first_name = d.get('first_name', '')
        existing.last_name = d.get('last_name', '')
        existing.license_plate = d.get('license_plate', '')

    # ---- Bookings (full replace) ----
    Booking.query.delete()
    for b in data.get('bookings', []):
        db.session.add(Booking(
            user_id=b.get('user_id', ''),
            driver_id=b.get('driver_id', 'unassigned'),
            date_time=b.get('date_time', ''),
            pickup=b.get('pickup', ''),
            dropoff=b.get('dropoff', ''),
            pickup_lat=b.get('pickup_lat'),
            pickup_lng=b.get('pickup_lng'),
            dropoff_lat=b.get('dropoff_lat'),
            dropoff_lng=b.get('dropoff_lng'),
            status=b.get('status', 'unassigned'),
            trip_start_time=b.get('trip_start_time'),
            trip_end_time=b.get('trip_end_time'),
        ))

    # ---- Waybills + Trip history (per driver) ----
    for username, d in data.get('drivers', {}).items():
        # Waybills: full replace for this driver
        Waybill.query.filter_by(driver_id=username).delete()
        for w in d.get('waybills', []):
            db.session.add(Waybill(
                driver_id=username,
                date=w.get('Date', '') or w.get('date', ''),
                time=w.get('Time', '') or w.get('time', ''),
                pickup=w.get('Pickup', '') or w.get('pickup', ''),
                dropoff=w.get('Dropoff', '') or w.get('dropoff', ''),
                cost=float(w.get('Cost', 0) or w.get('cost', 0) or 0),
                route=w.get('Route', '') or w.get('route', ''),
            ))

        # Trip history: full replace for this driver
        TripHistory.query.filter_by(driver_id=username).delete()
        for t in d.get('trip_history', []):
            db.session.add(TripHistory(
                driver_id=username,
                date=t.get('date', '') or t.get('Date', ''),
                time=t.get('time', '') or t.get('Time', ''),
                pickup=t.get('pickup', '') or t.get('Pickup', ''),
                dropoff=t.get('dropoff', '') or t.get('Dropoff', ''),
                cost=float(t.get('cost', 0) or t.get('Cost', 0) or 0),
                route=t.get('route', '') or t.get('Route', ''),
            ))

    db.session.commit()


# Initialize All Plugins
time_slot_manager = TimeSlotManager("transport.db")
business_analytics = BusinessAnalytics("transport.db")
admin_user_manager = AdminUserManager(load_data, save_data)
route_optimizer = RouteOptimizer(coords=LOCATION_COORDS)
real_time_tracker = RealTimeTracker()
campaign_registrar = CampaignBulkRegistration(load_data, save_data)
billing_mis = BillingMIS()


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    data = load_data()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user_data = data['users'].get(username)
        if user_data and check_password_hash(user_data['password'], password):
            user = User(username, user_data.get('is_admin', False), user_data.get('is_driver', False))
            login_user(user)
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            elif user.is_driver:
                return redirect(url_for('driver_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')



@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        data = load_data()
        user_id = current_user.get_id()
        user_data = data['users'].get(user_id)

        if not user_data:
            return render_template('change_password.html', error="User not found")

        if not check_password_hash(user_data['password'], current_pw):
            return render_template('change_password.html', error="Current password is incorrect")

        if len(new_pw) < 8:
            return render_template('change_password.html', error="New password must be at least 8 characters")

        if new_pw != confirm_pw:
            return render_template('change_password.html', error="New passwords do not match")

        user_data['password'] = generate_password_hash(new_pw)
        save_data(data)
        return render_template('change_password.html', success="Password updated successfully. Use it next time you log in.")

    return render_template('change_password.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/admin_add_driver', methods=['POST'])
@login_required
def admin_add_driver():
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    username = request.form['username']
    name = request.form['name']
    password = request.form['password']
    license_plate = request.form['license_plate']

    data = load_data()
    if username in data['users']:
        return "Username already exists", 409

    hashed_password = generate_password_hash(password)
    data['users'][username] = {
        'username': username,
        'name': name,
        'password': hashed_password,
        'is_admin': False,
        'is_driver': True,
        'registered_address': ''
    }
    data['drivers'][username] = {
        'first_name': name.split()[0] if ' ' in name else name,
        'last_name': name.split()[-1] if ' ' in name else '',
        'license_plate': license_plate,
        'waybills': [],
        'trip_history': []
    }
    save_data(data)
    return redirect(url_for('admin_dashboard', driver_added=True))


@app.route('/admin_add_agent', methods=['POST'])
@login_required
def admin_add_agent():
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    username = request.form['username']
    name = request.form['name']
    password = request.form['password']
    registered_address = request.form.get('registered_address', '')
    initial_allowance_raw = request.form.get('initial_allowance', '').strip()
    initial_allowance = float(initial_allowance_raw) if initial_allowance_raw else 0.0

    data = load_data()
    if username in data['users']:
        return "Username already exists", 409

    hashed_password = generate_password_hash(password)
    data['users'][username] = {
        'username': username,
        'name': name,
        'password': hashed_password,
        'is_admin': False,
        'is_driver': False,
        'registered_address': registered_address,
        'travel_allowance': initial_allowance,
        'penalties': []
    }
    save_data(data)
    return redirect(url_for('admin_dashboard', agent_added=True))


@app.route('/admin_apply_penalty', methods=['POST'])
@login_required
def admin_apply_penalty():
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    agent_id = request.form['agent_id']
    penalty_amount_raw = request.form.get('penalty_amount', '').strip()
    penalty_amount = float(penalty_amount_raw) if penalty_amount_raw else 50.00
    reason = request.form.get('reason', 'Penalty applied by Admin')

    data = load_data()
    if agent_id not in data['users'] or data['users'][agent_id].get('is_driver') or data['users'][agent_id].get('is_admin'):
        return "Invalid user ID or user is not an agent", 400

    data['users'][agent_id]['travel_allowance'] -= penalty_amount

    # Log the penalty
    penalty_record = {
        'amount': penalty_amount,
        'reason': reason,
        'timestamp': datetime.now().isoformat()
    }
    data['users'][agent_id]['penalties'].append(penalty_record)

    save_data(data)
    return redirect(url_for('admin_dashboard', penalty_applied=True))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        password = request.form['password']
        registered_address = request.form.get('registered_address', '')

        registered_lat = request.form.get('registered_lat', '').strip()
        registered_lng = request.form.get('registered_lng', '').strip()
        try:
            registered_lat = float(registered_lat) if registered_lat else None
            registered_lng = float(registered_lng) if registered_lng else None
        except ValueError:
            registered_lat = None
            registered_lng = None

        data = load_data()
        if username in data['users']:
            return render_template('register.html', error="Username already exists")

        hashed_password = generate_password_hash(password)
        data['users'][username] = {
            'username': username,
            'name': name,
            'password': hashed_password,
            'is_admin': False,
            'is_driver': False,
            'registered_address': registered_address,
            'registered_lat': registered_lat,
            'registered_lng': registered_lng,
            'travel_allowance': 0,
            'penalties': []
        }
        save_data(data)
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/register_driver', methods=['GET', 'POST'])
def register_driver():
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        password = request.form['password']
        license_plate = request.form['license_plate']

        data = load_data()
        if username in data['users']:
            return render_template('register_driver.html', error="Username already exists")

        hashed_password = generate_password_hash(password)
        data['users'][username] = {
            'username': username,
            'name': name,
            'password': hashed_password,
            'is_admin': False,
            'is_driver': True,
            'registered_address': ''
        }
        data['drivers'][username] = {
            'first_name': name.split()[0] if ' ' in name else name,
            'last_name': name.split()[-1] if ' ' in name else '',
            'license_plate': license_plate,
            'waybills': [],
            'trip_history': []
        }
        save_data(data)
        return redirect(url_for('login'))
    return render_template('register_driver.html')


@app.route('/user_dashboard')
@login_required
def user_dashboard():
    data = load_data()
    user_id = current_user.get_id()
    user_data = data.get('users', {}).get(user_id, {})
    user_bookings = [b for b in data['bookings'] if b.get('user_id') == user_id]

    # We need to give each booking a unique ID for the forms
    for i, booking in enumerate(user_bookings):
        booking['id'] = i

    # Fetch penalties from the user's data
    user_penalties = user_data.get('penalties', [])

    return render_template('user_dashboard.html', bookings=user_bookings, user_data=user_data, penalties=user_penalties)


@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))
    data = load_data()
    all_users = data.get('users', {})
    all_drivers = data.get('drivers', {})
    all_bookings = data.get('bookings', [])
    reset_success = request.args.get('reset_success')
    clear_success = request.args.get('clear_success')
    driver_added = request.args.get('driver_added')
    agent_added = request.args.get('agent_added')
    history_cleared = request.args.get('history_cleared')
    penalty_applied = request.args.get('penalty_applied')

    # Financial reporting data
    total_trips = sum(len(driver.get('trip_history', [])) for driver in all_drivers.values())
    total_cost = sum(trip.get('cost', 0) for driver in all_drivers.values() for trip in driver.get('trip_history', []))
    avg_cost_per_trip = total_cost / total_trips if total_trips > 0 else 0

    return render_template(
        'admin_dashboard.html',
        bookings=all_bookings,
        all_users=all_users,
        all_drivers=all_drivers,
        reset_success=reset_success,
        clear_success=clear_success,
        driver_added=driver_added,
        agent_added=agent_added,
        history_cleared=history_cleared,
        penalty_applied=penalty_applied,
        total_trips=total_trips,
        total_cost=total_cost,
        avg_cost_per_trip=avg_cost_per_trip
    )


@app.route('/driver_dashboard')
@login_required
def driver_dashboard():
    if not current_user.is_authenticated or not current_user.is_driver:
        return redirect(url_for('login'))
    data = load_data()
    driver_id = current_user.get_id()
    driver_bookings = data.get('driver_bookings', {}).get(driver_id, [])

    # Filter for assigned and in-progress bookings
    assigned_bookings = [b for b in data['bookings'] if b.get('driver_id') == driver_id and b.get('status') in ['assigned', 'in-progress']]

    return render_template('driver_dashboard.html', bookings=assigned_bookings)


@app.route('/upload_waybill', methods=['POST'])
@login_required
def upload_waybill():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))

    driver_id = request.form.get('driver_id')
    waybill_file = request.files.get('waybill_file')

    if not driver_id or not waybill_file:
        return "Missing driver ID or waybill file", 400

    data = load_data()
    if driver_id not in data.get('drivers', {}):
        return "Driver not found", 404

    # --- Read and normalize ---
    def norm(s):
        return (s or '').strip().lower().replace('_', ' ')

    def pick(row_norm, *candidates):
        for c in candidates:
            key = norm(c)
            if key in row_norm and row_norm[key] not in (None, ''):
                return row_norm[key]
        return ''

    def split_datetime(value):
        """'2026-09-13 18:00' or '2026-09-13T18:00' -> ('2026-09-13', '18:00')"""
        if not value:
            return '', ''
        s = str(value).strip()
        for sep in ('T', ' '):
            if sep in s:
                a, b = s.split(sep, 1)
                return a.strip(), b.strip()
        return s, ''

    try:
        raw = waybill_file.stream.read().decode('utf-8-sig')
        raw_rows = list(csv.DictReader(io.StringIO(raw)))
    except Exception as e:
        return f"Error reading CSV: {e}", 400

    if not raw_rows:
        return "CSV is empty", 400

    transformed = []
    for row in raw_rows:
        # Normalize keys: lowercase, strip, underscores -> spaces
        row_norm = {norm(k): v for k, v in row.items()}

        # Date and Time
        date_val = pick(row_norm, 'date', 'trip date', 'booking date')
        time_val = pick(row_norm, 'time', 'trip time', 'booking time')

        # Combined 'date/time' or 'datetime' column
        combined = pick(row_norm, 'date/time', 'datetime', 'date time',
                        'trip start time', 'start time')
        if combined and (not date_val or not time_val):
            d, t = split_datetime(combined)
            date_val = date_val or d
            time_val = time_val or t

        # Pickup
        pickup = pick(row_norm, 'pickup', 'from', 'origin',
                      'pickup location', 'start')

        # Dropoff
        dropoff = pick(row_norm, 'dropoff', 'to', 'destination',
                       'dropoff location', 'end')

        # Cost
        cost_raw = pick(row_norm, 'cost', 'amount', 'price', 'fare', 'charge')
        try:
            cost = float(str(cost_raw).replace('R', '').replace(',', '').strip() or 0)
        except ValueError:
            cost = 0.0

        # Route
        route = pick(row_norm, 'route', 'trip', 'description')
        if not route:
            route = f"{pickup} to {dropoff}" if pickup and dropoff else ''

        transformed.append({
            'Date': date_val,
            'Time': time_val,
            'Pickup': pickup,
            'Dropoff': dropoff,
            'Cost': cost,
            'Driver_ID': driver_id,
            'Route': route,
        })

    # Replace the driver's waybills with this batch (idempotent upload)
    data['drivers'][driver_id]['waybills'] = transformed
    save_data(data)

    return redirect(url_for('admin_dashboard'))


@app.route('/admin_process_waybills/<driver_id>', methods=['POST'])
@login_required
def admin_process_waybills(driver_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    data = load_data()
    driver_data = data.get('drivers', {}).get(driver_id)
    if not driver_data:
        return "Driver not found", 404

    pending = driver_data.get('waybills', [])
    if pending:
        driver_data.setdefault('trip_history', [])
        for w in pending:
            trip = {
                'date': w.get('Date', '') or w.get('date', ''),
                'time': w.get('Time', '') or w.get('time', ''),
                'pickup': w.get('Pickup', '') or w.get('pickup', ''),
                'dropoff': w.get('Dropoff', '') or w.get('dropoff', ''),
                'cost': float(w.get('Cost', 0) or w.get('cost', 0) or 0),
                'route': w.get('Route', '') or w.get('route', ''),
            }
            driver_data['trip_history'].append(trip)

            # Create an invoice for this trip
            db.session.add(Invoice(
                driver_id=driver_id,
                trip_date=trip['date'],
                trip_time=trip['time'],
                pickup=trip['pickup'],
                dropoff=trip['dropoff'],
                amount=trip['cost'],
                status='pending',
                created_at=datetime.now().isoformat(),
            ))

        driver_data['waybills'] = []
        save_data(data)
        db.session.commit()

    return redirect(url_for('admin_dashboard'))




@app.route('/admin_assign_driver/<int:booking_id>', methods=['POST'])
@login_required
def admin_assign_driver(booking_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    driver_id = request.form.get('driver_id', '').strip()
    if not driver_id:
        return "Missing driver_id", 400

    data = load_data()
    if driver_id not in data.get('drivers', {}):
        return "Driver not found", 404

    booking = Booking.query.get(booking_id)
    if not booking:
        return "Booking not found", 404

    booking.driver_id = driver_id
    if booking.status == 'unassigned':
        booking.status = 'assigned'
    db.session.commit()

    return redirect(url_for('admin_dashboard'))


@app.route('/export_data')
@login_required
def export_data():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))

    data = load_data()
    bookings = data.get('bookings', [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['User ID', 'Driver ID', 'Date/Time', 'From', 'To', 'Status', 'Trip Start Time', 'Trip End Time'])

    for booking in bookings:
        writer.writerow([
            booking.get('user_id', 'N/A'),
            booking.get('driver_id', 'N/A'),
            booking.get('date_time', 'N/A'),
            booking.get('pickup', 'N/A'),
            booking.get('dropoff', 'N/A'),
            booking.get('status', 'N/A'),
            booking.get('trip_start_time', 'N/A'),
            booking.get('trip_end_time', 'N/A')
        ])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=all_bookings.csv'})


@app.route('/export_invoicing_data')
@login_required
def export_invoicing_data():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))

    data = load_data()
    completed_bookings = [b for b in data.get('bookings', []) if b.get('status') == 'completed']

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['User ID', 'From', 'To', 'Trip Start Time', 'Trip End Time'])

    for booking in completed_bookings:
        writer.writerow([
            booking.get('user_id', 'N/A'),
            booking.get('pickup', 'N/A'),
            booking.get('dropoff', 'N/A'),
            booking.get('trip_start_time', 'N/A'),
            booking.get('trip_end_time', 'N/A')
        ])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=invoicing_report.csv'})


@app.route('/admin_clear_bookings', methods=['POST'])
@login_required
def admin_clear_bookings():
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    data = load_data()
    data['bookings'] = [b for b in data['bookings'] if b.get('status') != 'completed']
    save_data(data)
    return redirect(url_for('admin_dashboard', clear_success=True))


@app.route('/admin_clear_daily_bookings', methods=['POST'])
@login_required
def admin_clear_daily_bookings():
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    data = load_data()
    today_date = datetime.now().strftime('%Y-%m-%d')
    data['bookings'] = [b for b in data['bookings'] if b.get('date_time', '').split(' ')[0] >= today_date]
    save_data(data)
    return redirect(url_for('admin_dashboard', reset_success=True))


@app.route('/export_drivers_csv')
@login_required
def export_drivers_csv():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))

    data = load_data()
    drivers = data.get('drivers', {})

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Driver ID', 'First Name', 'Last Name', 'License Plate'])

    for driver_id, driver_data in drivers.items():
        writer.writerow([
            driver_id,
            driver_data.get('first_name', 'N/A'),
            driver_data.get('last_name', 'N/A'),
            driver_data.get('license_plate', 'N/A')
        ])

    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=drivers.csv'})


@app.route('/export_agents_csv')
@login_required
def export_agents_csv():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))

    data = load_data()
    users = data.get('users', {})
    agents = {u: i for u, i in users.items() if not i.get('is_admin') and not i.get('is_driver')}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Agent ID', 'Name', 'Registered Address', 'Travel Allowance', 'Penalties'])

    for agent_id, agent_data in agents.items():
        total_penalties = sum(p['amount'] for p in agent_data.get('penalties', []))
        writer.writerow([
            agent_id,
            agent_data.get('name', 'N/A'),
            agent_data.get('registered_address', 'N/A'),
            f"R {agent_data.get('travel_allowance', 0):.2f}",
            f"R {total_penalties:.2f}"
        ])

    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=agents.csv'})


@app.route('/export_penalty_history_csv')
@login_required
def export_penalty_history_csv():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))

    data = load_data()
    all_penalties = []
    for user_id, user_data in data.get('users', {}).items():
        for penalty in user_data.get('penalties', []):
            all_penalties.append({
                'agent_id': user_id,
                'amount': penalty.get('amount'),
                'reason': penalty.get('reason'),
                'timestamp': penalty.get('timestamp')
            })

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Agent ID', 'Amount', 'Reason', 'Timestamp'])

    for penalty in all_penalties:
        writer.writerow([
            penalty.get('agent_id', 'N/A'),
            f"R {penalty.get('amount', 0):.2f}",
            penalty.get('reason', 'N/A'),
            penalty.get('timestamp', 'N/A')
        ])

    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=penalty_history.csv'})


@app.route('/admin_driver_trip_history/<driver_id>')
@login_required
def admin_driver_trip_history(driver_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    data = load_data()
    driver_data = data.get('drivers', {}).get(driver_id)
    if not driver_data:
        return jsonify({"error": "Driver not found"}), 404

    return jsonify(driver_data.get('trip_history', []))


@app.route('/export_driver_trip_history_csv/<driver_id>')
@login_required
def export_driver_trip_history_csv(driver_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    data = load_data()
    driver_data = data.get('drivers', {}).get(driver_id)
    if not driver_data:
        return "Driver not found", 404

    trip_history = driver_data.get('trip_history', [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Time', 'Route', 'Pickup', 'Dropoff', 'Cost'])

    for trip in trip_history:
        writer.writerow([
            trip.get('date', 'N/A'),
            trip.get('time', 'N/A'),
            trip.get('route', 'N/A'),
            trip.get('pickup', 'N/A'),
            trip.get('dropoff', 'N/A'),
            trip.get('cost', 'N/A')
        ])

    output.seek(0)
    filename = f"{driver_id}_trip_history.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment;filename={filename}'})


@app.route('/admin_clear_driver_history/<driver_id>', methods=['POST'])
@login_required
def admin_clear_driver_history(driver_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    data = load_data()
    if driver_id not in data.get('drivers', {}):
        return "Driver not found", 404

    data['drivers'][driver_id]['trip_history'] = []
    save_data(data)
    return redirect(url_for('admin_dashboard', history_cleared=True))


@app.route('/get_driver_waybills')
@login_required
def get_driver_waybills():
    if not current_user.is_authenticated or not current_user.is_driver:
        return jsonify([])
    data = load_data()
    driver_id = current_user.get_id()
    driver_data = data.get('drivers', {}).get(driver_id, {})
    return jsonify(driver_data.get('waybills', []))


@app.route('/get_driver_trip_history')
@login_required
def get_driver_trip_history():
    if not current_user.is_authenticated or not current_user.is_driver:
        return jsonify([])
    data = load_data()
    driver_id = current_user.get_id()
    trip_history = data.get('drivers', {}).get(driver_id, {}).get('trip_history', [])
    return jsonify(trip_history)


@app.route('/get_driver_bookings')
@login_required
def get_driver_bookings():
    if not current_user.is_authenticated or not current_user.is_driver:
        return jsonify([])
    data = load_data()
    driver_id = current_user.get_id()
    driver_bookings = data.get('driver_bookings', {}).get(driver_id, [])
    return jsonify(driver_bookings)


@app.route('/admin_manage_users', methods=['POST'])
@login_required
def admin_manage_users():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))
    data = load_data()
    if 'remove_user' in request.form:
        user_to_remove = request.form['remove_user']
        if user_to_remove in data['users']:
            del data['users'][user_to_remove]
            data['bookings'] = [b for b in data['bookings'] if b['user_id'] != user_to_remove]
            save_data(data)
    return redirect(url_for('admin_dashboard'))


@app.route('/booking', methods=['GET', 'POST'])
@login_required
def booking():
    data = load_data()
    user_id = current_user.get_id()
    user_data = data.get('users', {}).get(user_id, {})
    user_address = user_data.get('registered_address', '') or ''

    all_locations = LOCATIONS.copy()
    if user_address and user_address not in all_locations:
        all_locations.append(user_address)

    def coords_for(location_name, current_user_data):
        """Return (lat, lng) for a location name."""
        if location_name in LOCATION_COORDS:
            return LOCATION_COORDS[location_name]
        # Match the user's own address
        if location_name == current_user_data.get('registered_address'):
            lat = current_user_data.get('registered_lat')
            lng = current_user_data.get('registered_lng')
            if lat is not None and lng is not None:
                return (lat, lng)
        return (None, None)

    if request.method == 'POST':
        driver_id = 'unassigned'
        date_time = request.form['date_time']
        pickup = request.form['pickup']
        dropoff = request.form['dropoff']

        if not all([date_time, pickup, dropoff]):
            return render_template('booking.html', locations=all_locations,
                                   time_slots=TIME_SLOTS,
                                   error="All fields are required.")

        pickup_lat, pickup_lng = coords_for(pickup, user_data)
        dropoff_lat, dropoff_lng = coords_for(dropoff, user_data)

        new_booking = {
            'user_id': user_id,
            'driver_id': driver_id,
            'date_time': date_time,
            'pickup': pickup,
            'dropoff': dropoff,
            'pickup_lat': pickup_lat,
            'pickup_lng': pickup_lng,
            'dropoff_lat': dropoff_lat,
            'dropoff_lng': dropoff_lng,
            'status': 'unassigned'
        }

        data['bookings'].append(new_booking)
        save_data(data)
        return redirect(url_for('user_dashboard'))

    return render_template('booking.html', locations=all_locations,
                           time_slots=TIME_SLOTS)




@app.route('/confirm_entry', methods=['POST'])
@login_required
def confirm_entry():
    if current_user.is_driver:
        return "Unauthorized", 403

    booking_index = int(request.form.get('booking_index'))
    data = load_data()
    user_bookings = [b for b in data['bookings'] if b['user_id'] == current_user.get_id()]

    if 0 <= booking_index < len(user_bookings):
        original_booking = user_bookings[booking_index]
        for booking in data['bookings']:
            if booking == original_booking:
                booking['status'] = 'in-progress'
                booking['trip_start_time'] = datetime.now().isoformat()
                save_data(data)
                break

    return redirect(url_for('user_dashboard'))


@app.route('/complete_trip', methods=['POST'])
@login_required
def complete_trip():
    if not current_user.is_authenticated or not current_user.is_driver:
        return "Unauthorized", 401

    booking_id = request.form.get('booking_id')
    data = load_data()
    bookings = data['bookings']

    booking_found = False
    for booking in bookings:
        unique_id = f"{booking['user_id']}-{booking['pickup']}-{booking['dropoff']}-{booking['date_time']}"
        if unique_id == booking_id and booking['status'] == 'in-progress':
            booking['status'] = 'completed'
            booking['trip_end_time'] = datetime.now().isoformat()
            booking_found = True
            break

    if booking_found:
        save_data(data)
        return redirect(url_for('driver_dashboard'))
    else:
        return "In-progress booking not found", 404


# ===== PLUGIN ROUTES =====

@app.route('/admin/time_slots', methods=['GET', 'POST'])
@login_required
def admin_time_slots():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))
    time_slot_mgr = TimeSlotManager("transport.db")
    if request.method == 'POST':
        slot = request.form.get('slot', '').strip()
        campaign = request.form.get('campaign', '').strip()
        if campaign and slot:
            time_slot_mgr.set_campaign_slot(campaign, slot, True)
        elif slot:
            time_slot_mgr.set_global_slot(slot, True)
    global_settings = time_slot_mgr.get_global_settings()
    campaign_slots = time_slot_mgr.get_campaign_slots()
    return render_template('admin_time_slots.html', global_settings=global_settings, campaign_slots=campaign_slots)


@app.route('/admin/analytics')
@login_required
def admin_analytics():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))
    business_analytics = BusinessAnalytics("transport.db")
    metrics = business_analytics.get_dashboard_metrics()
    return render_template('admin_analytics.html', metrics=metrics)


@app.route('/admin/user_management')
@login_required
def admin_user_management():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))
    user_mgr = UserManager("transport.db")
    users = user_mgr.get_all_users()
    return render_template('admin_user_management.html', users=users)


@app.route('/admin/bulk_register', methods=['GET', 'POST'])
@login_required
def admin_bulk_register():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))
    if request.method == 'POST':
        csv_text = request.form.get('csv_text', '')
        created, errors = campaign_registrar.bulk_register_from_csv(csv_text)
        return render_template('admin_bulk_register.html', created=created, errors=errors)
    return render_template('admin_bulk_register.html')


# ===== BILLING ROUTES =====
@app.route('/admin/billing')
@login_required
def admin_billing():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('login'))

    invoices = Invoice.query.order_by(Invoice.id.desc()).all()
    total_revenue = sum(i.amount for i in invoices if i.status == 'paid')
    pending_invoices = [i for i in invoices if i.status == 'pending']
    paid_invoices = [i for i in invoices if i.status == 'paid']
    pending_amount = sum(i.amount for i in pending_invoices)

    completion_rate = 0.0
    if invoices:
        completion_rate = round(len(paid_invoices) / len(invoices) * 100, 2)

    overview = {
        'total_revenue': total_revenue,
        'pending_invoices': len(pending_invoices),
        'paid_invoices': len(paid_invoices),
        'pending_amount': pending_amount,
        'revenue_trend': 0,
        'completion_rate': completion_rate,
    }

    return render_template('admin_billing.html', overview=overview, invoices=invoices)


@app.route('/admin/mark_invoice_paid/<int:invoice_id>', methods=['POST'])
@login_required
def admin_mark_invoice_paid(invoice_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403
    inv = Invoice.query.get(invoice_id)
    if not inv:
        return "Invoice not found", 404
    inv.status = 'paid'
    inv.paid_at = datetime.now().isoformat()
    db.session.commit()
    return redirect(url_for('admin_billing'))


@app.route('/admin/delete_invoice/<int:invoice_id>', methods=['POST'])
@login_required
def admin_delete_invoice(invoice_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403
    inv = Invoice.query.get(invoice_id)
    if inv:
        db.session.delete(inv)
        db.session.commit()
    return redirect(url_for('admin_billing'))




# ===== ROUTE OPTIMIZER ROUTES =====
@app.route('/api/driver_position', methods=['POST'])
def api_driver_position():
    """
    Driver posts their GPS position.
    Auth: must be logged in as a driver (or admin for the simulator).
    """
    if not current_user.is_authenticated:
        return jsonify({'error': 'not logged in'}), 401

    payload = request.get_json(silent=True) or {}

    # Drivers can only report for themselves; admins can report for anyone
    if current_user.is_driver:
        driver_id = current_user.get_id()
    else:
        driver_id = (payload.get('driver_id') or '').strip()

    if not driver_id:
        return jsonify({'error': 'missing driver_id'}), 400

    try:
        lat = float(payload.get('lat'))
        lng = float(payload.get('lng'))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid lat/lng'}), 400

    real_time_tracker.update_position(
        driver_id,
        lat, lng,
        speed=payload.get('speed', 0),
        heading=payload.get('heading', 0),
        route=payload.get('route', ''),
    )
    return jsonify({'ok': True})


@app.route('/api/positions')
@login_required
def api_positions():
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({}), 403
    return jsonify(real_time_tracker.get_all_latest_positions())


@app.route('/api/track/<driver_id>')
@login_required
def api_track(driver_id):
    """Return last N minutes of positions for a driver (for the map trail)."""
    if not current_user.is_authenticated:
        return jsonify([]), 401
    # Drivers can only see their own track
    if current_user.is_driver and current_user.get_id() != driver_id:
        return jsonify([]), 403
    minutes = int(request.args.get('minutes', 60))
    return jsonify(real_time_tracker.get_track(driver_id, minutes=minutes))


@app.route('/driver/location')
@login_required
def driver_location():
    if not current_user.is_authenticated or not current_user.is_driver:
        return redirect(url_for('login'))
    return render_template('driver_location.html')


@app.route('/admin/simulate_tracking', methods=['POST'])
@login_required
def admin_simulate_tracking():
    """Move all drivers randomly around Johannesburg. Demo helper."""
    import random
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403

    data = load_data()
    driver_ids = list(data.get('drivers', {}).keys())

    if not driver_ids:
        return redirect(url_for('admin_live_tracking'))

    spots = [
        (-26.2041, 28.0473),
        (-26.1076, 28.0567),
        (-26.1438, 28.0957),
        (-26.1999, 28.0455),
    ]

    for i, did in enumerate(driver_ids):
        base_lat, base_lng = spots[i % len(spots)]
        existing = real_time_tracker.get_latest_position(did)

        if existing:
            lat = existing.lat + random.uniform(-0.003, 0.003)
            lng = existing.lng + random.uniform(-0.003, 0.003)
        else:
            lat = base_lat + random.uniform(-0.005, 0.005)
            lng = base_lng + random.uniform(-0.005, 0.005)

        real_time_tracker.update_position(
            did, lat, lng,
            speed=random.uniform(20, 80),
            heading=random.uniform(0, 360),
            route='Demo route',
        )

    return redirect(url_for('admin_live_tracking'))


@app.route('/admin/clear_tracking', methods=['POST'])
@login_required
def admin_clear_tracking():
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Unauthorized", 403
    real_time_tracker.clear()
    return redirect(url_for('admin_live_tracking'))




@app.route('/admin/route_optimizer')
@login_required
def admin_route_optimizer():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect('/login')
    overview = {
        "total_routes": 0,
        "optimized_routes": 0,
        "fuel_savings": 0,
        "total_distance": 0,
        "time_savings": 0,
        "optimization_rate": 0
    }
    return render_template('admin_route_optimizer.html', overview=overview)


# ===== LIVE TRACKING ROUTES =====
@app.route('/admin/live_tracking')
@login_required
def admin_live_tracking():
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect('/login')
    overview = real_time_tracker.get_overview()
    data = load_data()
    drivers = list(data.get('drivers', {}).keys())
    return render_template('admin_live_tracking.html',
                           overview=overview, drivers=drivers)




if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
