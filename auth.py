from flask import Blueprint, request, render_template, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin
from werkzeug.security import check_password_hash
import os

auth_bp = Blueprint("auth", __name__)
login_manager = LoginManager()

class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role

users = {
    "admin": os.getenv("ADMIN_PASSWORD_HASH")
}

@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return User("admin", "admin")
    if str(user_id).isdigit():
        return User(user_id, "agent")
    return None


def admin_required(f):
    from functools import wraps
    from flask_login import current_user

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            return "Forbidden", 403
        return f(*args, **kwargs)
    return wrapper


def agent_required(f):
    from functools import wraps
    from flask_login import current_user

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "agent":
            return "Forbidden", 403
        return f(*args, **kwargs)
    return wrapper


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if check_password_hash(users["admin"], request.form["password"]):
            login_user(User("admin", "admin"))
            return redirect("/")
        flash("Invalid login")
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")