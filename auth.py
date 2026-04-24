import os
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, render_template, redirect, flash, url_for
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

def init_auth(app):
    login_manager.init_app(app)

# ======================
# USER MODEL
# ======================
class User(UserMixin):
    def __init__(self, id, username, role, province=None, district=None):
        self.id = str(id)
        self.username = username
        self.role = role
        self.province = province
        self.district = district

# ======================
# LOAD USER
# ======================
@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, username, role, province, district
        FROM users
        WHERE id=%s AND is_active=TRUE
    """, (user_id,))

    row = cur.fetchone()

    cur.close()
    conn.close()

    if row:
        return User(*row)

    return None

# ======================
# ROLE CONTROL
# ======================
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))

            if current_user.role not in roles:
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

        if not username or not password:
            flash("Username and password required")
            return render_template("login.html")

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, username, password_hash, role,
                   failed_attempts, province, district
            FROM users
            WHERE username=%s AND is_active=TRUE
        """, (username,))

        user = cur.fetchone()

        if not user:
            flash("Invalid credentials")
            return render_template("login.html")

        # 🔴 LOCKOUT CONTROL
        if user[4] >= 5:
            flash("Account locked. Contact admin.")
            return render_template("login.html")

        # ✅ PASSWORD CHECK
        if check_password_hash(user[2], password):

            login_user(User(
                id=user[0],
                username=user[1],
                role=user[3],
                province=user[5],
                district=user[6]
            ))

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

            # 🔁 SMART REDIRECT (ROLE-BASED)
            if user[3] == "admin":
                return redirect(url_for("dashboard"))

            elif user[3] == "national":
                return redirect(url_for("war_room"))

            elif user[3] == "provincial":
                return redirect(url_for("provincial_dashboard"))

            else:
                return redirect(url_for("agent_dashboard"))

        else:
            # ❌ WRONG PASSWORD
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
    return redirect(url_for("auth.login"))

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
        province = request.form.get("province")
        district = request.form.get("district")

        if not username or not password:
            flash("Username and password required")
            return redirect(url_for("auth.create_user"))

        if role not in ["admin", "national", "provincial", "agent"]:
            flash("Invalid role")
            return redirect(url_for("auth.create_user"))

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO users 
                (username, password_hash, role, province, district)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                username,
                generate_password_hash(password),
                role,
                province,
                district
            ))

            conn.commit()
            flash(f"User '{username}' created")

        except Exception as e:
            conn.rollback()
            print("CREATE USER ERROR:", e)
            flash("User already exists or error")

        finally:
            cur.close()
            conn.close()

        return redirect(url_for("auth.create_user"))

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

    return redirect(url_for("dashboard"))

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
