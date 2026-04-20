import os
import psycopg2
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, flash
from dotenv import load_dotenv
from functools import wraps

from flask_login import login_required, current_user

# ✅ NEW AUTH SYSTEM
from auth import auth_bp, login_manager, seed_admin, role_required

load_dotenv()

# ======================
# CREATE APP
# ======================
app = Flask(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is required")

app.secret_key = SECRET_KEY

# ======================
# SESSION SECURITY
# ======================
ENV = os.getenv("ENV", "development")

app.config["SESSION_COOKIE_SECURE"] = ENV == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ======================
# INIT AUTH (CRITICAL)
# ======================
login_manager.init_app(app)
login_manager.login_view = "auth.login"

app.register_blueprint(auth_bp)

# ======================
# DATABASE
# ======================
def get_db():
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        return psycopg2.connect(
            host="localhost",
            database="membership_db",
            user="postgres",
            password=os.getenv("DB_PASSWORD")
        )

    return psycopg2.connect(db_url, sslmode="require")

# ======================
# SEED ADMIN
# ======================
with app.app_context():
    seed_admin()

# ======================
# ROLE SHORTCUT (OPTIONAL)
# ======================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            return "Forbidden", 403
        return f(*args, **kwargs)
    return wrapper

# ======================
# HOME DASHBOARD
# ======================
@app.route("/")
@login_required
@role_required("admin")
def dashboard():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM members WHERE status='Active'")
    total_members = cur.fetchone()[0]

    cur.close()
    conn.close()

    return render_template("index.html", total_members=total_members)

# ======================
# MEMBERS (PAGINATED + SECURE)
# ======================
@app.route("/members")
@login_required
@role_required("admin", "manager")
def members():

    page = int(request.args.get("page", 1))
    per_page = 25
    offset = (page - 1) * per_page

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT membership_id, full_name, province, district, constituency, phone, status
        FROM members
        WHERE is_deleted = FALSE
        ORDER BY full_name
        LIMIT %s OFFSET %s
    """, (per_page, offset))

    rows = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM members WHERE is_deleted = FALSE")
    total = cur.fetchone()[0]

    cur.close()
    conn.close()

    members = [
        {
            "membership_id": r[0],
            "full_name": r[1],
            "province": r[2],
            "district": r[3],
            "constituency": r[4],
            "phone": r[5],
            "status": r[6]
        }
        for r in rows
    ]

    return render_template(
        "members.html",
        members=members,
        page=page,
        total_pages=(total // per_page) + 1
    )

# ======================
# EDIT MEMBER
# ======================
@app.route("/edit/<membership_id>", methods=["GET", "POST"])
@login_required
@role_required("admin", "manager")
def edit_member(membership_id):

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()

        if not full_name:
            return "Full name required", 400

        cur.execute("""
            UPDATE members
            SET full_name=%s,
                province=%s,
                district=%s,
                constituency=%s,
                phone=%s,
                status=%s,
                updated_at = CURRENT_TIMESTAMP
            WHERE membership_id=%s
        """, (
            full_name,
            request.form["province"],
            request.form["district"],
            request.form["constituency"],
            request.form["phone"],
            request.form["status"],
            membership_id
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect("/members")

    cur.execute("SELECT * FROM members WHERE membership_id=%s", (membership_id,))
    row = cur.fetchone()

    if not row:
        return "Member not found"

    columns = [d[0] for d in cur.description]
    member = dict(zip(columns, row))

    cur.close()
    conn.close()

    return render_template("edit_member.html", member=member)

# ======================
# SOFT DELETE
# ======================
@app.route("/delete/<membership_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_member(membership_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE members
        SET is_deleted = TRUE
        WHERE membership_id = %s
    """, (membership_id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/members")

# ======================
# SEARCH
# ======================
@app.route("/search")
@login_required
def search():

    q = request.args.get("q", "").strip().lower()

    if not q:
        return jsonify([])

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT membership_id, full_name, phone, province, district, constituency, status
        FROM members
        WHERE is_deleted = FALSE
        AND (LOWER(full_name) LIKE %s OR LOWER(phone) LIKE %s)
        ORDER BY full_name
        LIMIT 50
    """, (f"%{q}%", f"%{q}%"))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify([
        {
            "membership_id": r[0],
            "full_name": r[1],
            "phone": r[2],
            "province": r[3],
            "district": r[4],
            "constituency": r[5],
            "status": r[6]
        }
        for r in rows
    ])

# ======================
# HEALTH CHECK
# ======================
@app.route("/health")
def health():
    return {"status": "ok"}

# ======================
# RUN
# ======================
if __name__ == "__main__":
    app.run(debug=True)
