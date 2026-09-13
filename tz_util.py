from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    APP_TZ = ZoneInfo("Africa/Johannesburg")
except Exception:
    APP_TZ = None


def now_local():
    """Current time in app timezone (Cape Town)."""
    if APP_TZ:
        return datetime.now(APP_TZ)
    return datetime.now()


def now_iso():
    """Current time as ISO string in app timezone."""
    return now_local().isoformat()
