import csv
import io


class CampaignBulkRegistration:
    def __init__(self, load_data, save_data):
        self.load_data = load_data
        self.save_data = save_data

    def bulk_register_from_csv(self, csv_text):
        """
        CSV columns: username,name,password,registered_address
        Returns (created_count, errors)
        """
        from werkzeug.security import generate_password_hash

        reader = csv.DictReader(io.StringIO(csv_text))
        data = self.load_data()
        users = data.setdefault("users", {})
        created = 0
        errors = []

        for i, row in enumerate(reader, start=2):
            username = (row.get("username") or "").strip()
            name = (row.get("name") or "").strip()
            password = (row.get("password") or "").strip()
            address = (row.get("registered_address") or "").strip()

            if not username or not password:
                errors.append(f"Row {i}: missing username or password")
                continue
            if username in users:
                errors.append(f"Row {i}: username '{username}' already exists")
                continue

            users[username] = {
                "username": username,
                "name": name or username,
                "password": generate_password_hash(password),
                "is_admin": False,
                "is_driver": False,
                "registered_address": address,
                "travel_allowance": 0,
                "penalties": []
            }
            created += 1

        self.save_data(data)
        return created, errors
