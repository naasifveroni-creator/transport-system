# TFA Shuttles Transport System

A Flask-based shuttle booking and transport management system with role-based dashboards for admins, drivers, and agents.

## Features

- Login and registration for admins, drivers, and agents
- Booking system with pickup/dropoff and time slots
- Admin dashboard: user, driver, and agent management
- Driver dashboard with waybill upload and trip history
- Penalty and travel allowance tracking
- CSV exports: bookings, invoicing, drivers, agents, penalties, trip history
- Plugin modules: time slots, analytics, route optimization, live tracking, billing, bulk registration

## Tech Stack

- Python 3.10+
- Flask 3
- Flask-Login
- SQLite (for plugin data)
- JSON (for core app data)

## Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
   cd YOUR_REPO
   ```

2. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate    # Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the app:
   ```bash
   python3 app.py
   ```

5. Open http://localhost:5000

## Default Admin

- Username: `admin`
- Password: `password`

**Change this immediately in any real deployment.**

## Project Structure

```
.
├── app.py
├── requirements.txt
├── .gitignore
├── README.md
├── plugins/
│   ├── __init__.py
│   ├── time_slot_manager.py
│   ├── booking_enhancements.py
│   ├── business_analytics.py
│   ├── user_manager.py
│   ├── admin_enhancements.py
│   ├── route_optimizer.py
│   ├── realtime_tracking.py
│   ├── campaign_registration.py
│   └── billing_mis.py
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── register_driver.html
│   ├── user_dashboard.html
│   ├── admin_dashboard.html
│   ├── driver_dashboard.html
│   ├── booking.html
│   ├── admin_time_slots.html
│   ├── admin_analytics.html
│   ├── admin_user_management.html
│   ├── admin_bulk_register.html
│   ├── admin_billing.html
│   ├── admin_route_optimizer.html
│   └── admin_live_tracking.html
└── static/
    ├── css/style.css
    └── js/app.js
```

## Runtime Files (not tracked)

- `tfa_shuttles_data.json` — main JSON data store
- `transport.db` — SQLite DB used by plugins

## License

MIT
