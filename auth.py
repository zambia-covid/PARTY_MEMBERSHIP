import os
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, render_template, redirect, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db

auth_bp = Blueprint("auth", __name__)

# ======================
# LOGIN MANAGER
# ======================
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.session_protection = "strong"

# ======================
# USER MODEL
# ======================
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = str(id)
        self.username = username
        self.role = role

# ======================
# LOAD USER
# ======================
@login_manager.user_loader
def load_user(user_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, username, role
        FROM users
        WHERE id=%s AND is_active=TRUE
    """, (user_id,))

    row = cur.fetchone()

    cur.close()
    conn.close()

    if row:
        return User(row[0], row[1], row[2])

    return None

# ======================
# ROLE CONTROL
# ======================
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                return "Forbidden", 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ======================
# LOGIN
# ======================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, username, password_hash, role, failed_attempts
            FROM users
            WHERE username=%s AND is_active=TRUE
        """, (username,))

        user = cur.fetchone()

        if not user:
            flash("Invalid credentials")
            return render_template("login.html")

        # 🔴 LOCKOUT (5 failed attempts)
        if user[4] >= 5:
            flash("Account locked. Contact admin.")
            return render_template("login.html")

        if check_password_hash(user[2], password):

            login_user(User(user[0], user[1], user[3]))

            # reset attempts + update login time
            cur.execute("""
                UPDATE users
                SET failed_attempts=0,
                    last_login=%s
                WHERE id=%s
            """, (datetime.utcnow(), user[0]))

            conn.commit()

            cur.close()
            conn.close()

            return redirect("/")

        else:
            # increment failed attempts
            cur.execute("""
                UPDATE users
                SET failed_attempts = failed_attempts + 1
                WHERE id=%s
            """, (user[0],))

            conn.commit()

            cur.close()
            conn.close()

            flash("Invalid credentials")

    return render_template("login.html")

# ======================
# LOGOUT
# ======================
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# ======================
# CREATE USER (ADMIN ONLY)
# ======================
@auth_bp.route("/create_user", methods=["GET", "POST"])
@login_required
@role_required("admin")
def create_user():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "agent")

        if not username or not password:
            flash("Username and password required")
            return redirect("/create_user")

        if role not in ["admin", "manager", "agent"]:
            flash("Invalid role")
            return redirect("/create_user")

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO users (username, password_hash, role)
                VALUES (%s, %s, %s)
            """, (
                username,
                generate_password_hash(password),
                role
            ))

            conn.commit()

            flash(f"User '{username}' created")

        except Exception:
            conn.rollback()
            flash("User already exists or error")

        finally:
            cur.close()
            conn.close()

        return redirect("/create_user")

    return render_template("create_user.html")

# ======================
# DEACTIVATE USER
# ======================
@auth_bp.route("/deactivate_user/<int:user_id>", methods=["POST"])
@login_required
@role_required("admin")
def deactivate_user(user_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET is_active = FALSE
        WHERE id = %s
    """, (user_id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/")

# ======================
# SEED ADMIN
# ======================
def seed_admin():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE username='admin'")
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, %s)
        """, (
            "admin",
            generate_password_hash(os.getenv("ADMIN_PASSWORD")),
            "admin"
        ))
        conn.commit()

    cur.close()
    conn.close()
