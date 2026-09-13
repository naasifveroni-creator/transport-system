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
app.secret_key = 'your_secret_key_here'

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
LOCATIONS = ['Blvd', 'Match Factory', 'Adderly', 'Wembly Sqr', 'Campus A', 'Campus B', 'Campus C', 'Downtown', 'Airport', 'Train Station']
TIME_SLOTS = ['6pm', '7pm', '8pm', '9pm', '10pm', '11pm', '12pm', '12am', '1am', '2am', '3am', '4am', '5am', '6am']


def load_data():
    if not os.path.exists('tfa_shuttles_data.json'):
        with open('tfa_shuttles_data.json', 'w') as f:
            admin_password = generate_password_hash('password')
            initial_data = {
                'users': {
                    'admin': {
                        'username': 'admin',
                        'name': 'Admin User',
                        'password': admin_password,
                        'is_admin': True,
                        'is_driver': False,
                        'registered_address': 'Admin Headquarters',
                        'travel_allowance': 0,
                        'penalties': []
                    }
                },
                'bookings': [],
                'drivers': {},
                'driver_bookings': {}
            }
            json.dump(initial_data, f, indent=4)
    with open('tfa_shuttles_data.json', 'r') as f:
        data = json.load(f)

    # Add travel_allowance and penalties to existing users if they don't have it
    for username, user_data in data.get('users', {}).items():
        if 'travel_allowance' not in user_data:
            user_data['travel_allowance'] = 0
        if 'penalties' not in user_data:
            user_data['penalties'] = []

    save_data(data)
    return data


def save_data(data):
    with open('tfa_shuttles_data.json', 'w') as f:
        json.dump(data, f, indent=4)


# Initialize All Plugins
time_slot_manager = TimeSlotManager("transport.db")
business_analytics = BusinessAnalytics("transport.db")
admin_user_manager = AdminUserManager(load_data, save_data)
route_optimizer = RouteOptimizer("transport.db")
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
    initial_allowance = float(request.form.get('initial_allowance', 0))

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
    penalty_amount = float(request.form.get('penalty_amount', 50.00))
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

    try:
        waybill_content = waybill_file.stream.read().decode('utf-8')
        raw_waybill_data = list(csv.DictReader(io.StringIO(waybill_content)))

        # TRANSFORM DATA - THIS FIXES THE UNDEFINED ISSUE
        transformed_waybill_data = []
        for row in raw_waybill_data:
            transformed_row = {
                'Date': row.get('Date') or row.get('date') or '',
                'Time': row.get('Time') or row.get('time') or '',
                'Pickup': row.get('Pickup') or row.get('pickup') or row.get('From') or '',
                'Dropoff': row.get('Dropoff') or row.get('dropoff') or row.get('To') or '',
                'Cost': float(row.get('Cost') or row.get('cost') or 0),
                'Driver_ID': row.get('Driver_ID') or row.get('driver_id') or driver_id,
                'Route': row.get('Route') or row.get('route') or f"{row.get('Pickup', '')} to {row.get('Dropoff', '')}"
            }
            transformed_waybill_data.append(transformed_row)

    except Exception as e:
        return f"Error processing CSV: {e}", 400

    if 'waybills' not in data['drivers'][driver_id]:
        data['drivers'][driver_id]['waybills'] = []

    data['drivers'][driver_id]['waybills'].extend(transformed_waybill_data)
    save_data(data)
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
    waybills_to_display = driver_data.get('waybills', [])

    if waybills_to_display:
        driver_data.setdefault('trip_history', [])
        driver_data['trip_history'].extend(waybills_to_display)
        driver_data['waybills'].clear()
        save_data(data)
    return jsonify(waybills_to_display)


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
    user_address = user_data.get('registered_address', 'Unknown Location')

    all_locations = LOCATIONS.copy()
    if user_address and user_address not in all_locations:
        all_locations.append(user_address)

    if request.method == 'POST':
        driver_id = 'unassigned'
        date_time = request.form['date_time']
        pickup = request.form['pickup']
        dropoff = request.form['dropoff']

        if not all([date_time, pickup, dropoff]):
            return render_template('booking.html', locations=all_locations, time_slots=TIME_SLOTS, error="All fields are required.")

        new_booking = {
            'user_id': user_id,
            'driver_id': driver_id,
            'date_time': date_time,
            'pickup': pickup,
            'dropoff': dropoff,
            'status': 'unassigned'
        }

        data['bookings'].append(new_booking)
        save_data(data)
        return redirect(url_for('user_dashboard'))

    return render_template('booking.html', locations=all_locations, time_slots=TIME_SLOTS)


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
        return redirect('/login')
    overview = {
        "total_revenue": 0,
        "pending_invoices": 0,
        "paid_invoices": 0,
        "pending_amount": 0,
        "revenue_trend": 0,
        "completion_rate": 0
    }
    return render_template('admin_billing.html', overview=overview)


# ===== ROUTE OPTIMIZER ROUTES =====
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
    overview = {
        "total_vehicles": 0,
        "active_vehicles": 0,
        "idle_vehicles": 0,
        "avg_speed": 0,
        "on_time_rate": 0,
        "delivery_completion": 0
    }
    return render_template('admin_live_tracking.html', overview=overview)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
