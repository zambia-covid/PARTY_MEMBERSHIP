from flask import Blueprint, request, render_template, redirect, url_for, flash
from flask_login import login_user
from werkzeug.security import check_password_hash
import os

auth_bp = Blueprint("auth", __name__)

# Simple user class for Flask-Login
class AdminUser:
    def __init__(self, id):
        self.id = id

    def is_active(self):
        return True

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id


def get_admin_hash():
    return os.getenv("ADMIN_PASSWORD_HASH")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        password = request.form.get("password")

        if not password:
            flash("Password is required", "error")
            return render_template("login.html")

        stored_hash = get_admin_hash()

        # 🚨 Hard failure if config is broken
        if not stored_hash:
            return "Server error: ADMIN_PASSWORD_HASH missing", 500

        # ✅ Password check
        if check_password_hash(stored_hash, password):

            user = AdminUser(id="admin")
            login_user(user)

            # redirect to next page or default
            next_page = request.args.get("next")
            return redirect(next_page or url_for("members.members"))

        else:
            flash("Invalid password", "error")

    return render_template("login.html")
