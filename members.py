from flask import Blueprint, request, redirect, url_for, render_template
from flask_login import login_required
from auth import admin_required
from db import get_db
import uuid

# ✅ DEFINE ONCE
members_bp = Blueprint("members", __name__)

# =========================
# REGISTRATION PAGE
# =========================
@members_bp.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")


# =========================
# HANDLE REGISTRATION
# =========================
@members_bp.route("/register", methods=["POST"])
def register_member():

    full_name = request.form.get("full_name")
    province = request.form.get("province")
    district = request.form.get("district")
    constituency = request.form.get("constituency")
    ward = request.form.get("ward")
    phone = request.form.get("phone")

    membership_id = str(uuid.uuid4())[:8].upper()

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO members 
        (membership_id, full_name, province, district, constituency, ward, phone, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'Active')
    """, (
        membership_id,
        full_name,
        province,
        district,
        constituency,
        ward,
        phone
    ))

    conn.commit()
    cur.close()
    conn.close()

    # redirect after success
    return redirect(url_for("members.register_page"))


# =========================
# MEMBERS LIST (ADMIN)
# =========================
@members_bp.route("/members")
@login_required
@admin_required
def members():

    q = request.args.get("q", "").strip().lower()

    conn = get_db()
    cur = conn.cursor()

    if q:
        cur.execute("""
            SELECT membership_id, full_name, phone, province, constituency, status
            FROM members
            WHERE LOWER(full_name) LIKE %s OR LOWER(phone) LIKE %s
            ORDER BY full_name
            LIMIT 100
        """, (f"%{q}%", f"%{q}%"))
    else:
        cur.execute("""
            SELECT membership_id, full_name, phone, province, constituency, status
            FROM members
            ORDER BY full_name
            LIMIT 100
        """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("members.html", members=rows)
