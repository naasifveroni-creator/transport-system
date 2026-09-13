from werkzeug.security import generate_password_hash
from models import db, DBUser as User, Driver


class UserManager:
    def __init__(self, db_path=None):
        pass

    def get_all_users(self):
        return [
            {
                "username": u.username,
                "name": u.name,
                "is_admin": u.is_admin,
                "is_driver": u.is_driver,
                "registered_address": u.registered_address or '',
                "travel_allowance": u.travel_allowance or 0.0,
            }
            for u in User.query.order_by(User.username).all()
        ]

    def get_user(self, username):
        u = User.query.get(username)
        if not u:
            return None
        return {
            "username": u.username,
            "name": u.name,
            "is_admin": u.is_admin,
            "is_driver": u.is_driver,
            "registered_address": u.registered_address or '',
            "travel_allowance": u.travel_allowance or 0.0,
        }

    def create_user(self, username, name, password,
                    is_admin=False, is_driver=False, registered_address=""):
        if User.query.get(username):
            raise ValueError(f"User {username} already exists")
        u = User(
            username=username,
            name=name,
            password=generate_password_hash(password),
            is_admin=is_admin,
            is_driver=is_driver,
            registered_address=registered_address,
            travel_allowance=0.0,
        )
        db.session.add(u)
        db.session.commit()
        return u

    def delete_user(self, username):
        u = User.query.get(username)
        if not u:
            return False
        db.session.delete(u)
        db.session.commit()
        return True
