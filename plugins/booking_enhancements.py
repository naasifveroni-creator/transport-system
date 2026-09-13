from datetime import datetime
from tz_util import now_local, now_iso

DEFAULT_SLOTS = [
    '6pm', '7pm', '8pm', '9pm', '10pm', '11pm', '12pm',
    '12am', '1am', '2am', '3am', '4am', '5am', '6am'
]


def get_available_time_slots(db_path="transport.db"):
    """Return list of enabled time slots."""
    try:
        from plugins.time_slot_manager import TimeSlotManager
        mgr = TimeSlotManager(db_path)
        slots = [s['slot'] for s in mgr.get_global_settings() if s['enabled']]
        return slots or DEFAULT_SLOTS
    except Exception:
        return DEFAULT_SLOTS


def validate_booking_time(date_time_str):
    """Return (ok, message). Basic sanity check."""
    if not date_time_str:
        return False, "Missing date/time."
    try:
        dt = datetime.fromisoformat(date_time_str.replace('Z', ''))
    except ValueError:
        return False, "Invalid date/time format."
    if dt < now_local():
        return False, "Booking time is in the past."
    return True, ""
