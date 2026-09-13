class AdminUserManager:
    """
    Wrapper around the JSON data store used by app.py.
    Pass in load_data and save_data callables.
    """
    def __init__(self, load_data, save_data):
        self.load_data = load_data
        self.save_data = save_data

    def list_agents(self):
        data = self.load_data()
        return {
            u: info for u, info in data.get("users", {}).items()
            if not info.get("is_admin") and not info.get("is_driver")
        }

    def list_drivers(self):
        data = self.load_data()
        return data.get("drivers", {})

    def apply_penalty(self, username, amount, reason="Penalty applied"):
        from datetime import datetime
        data = self.load_data()
        user = data.get("users", {}).get(username)
        if not user or user.get("is_admin") or user.get("is_driver"):
            return False
        user["travel_allowance"] = user.get("travel_allowance", 0) - float(amount)
        user.setdefault("penalties", []).append({
            "amount": float(amount),
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })
        self.save_data(data)
        return True
