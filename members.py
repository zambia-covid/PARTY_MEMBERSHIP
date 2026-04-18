from flask import Blueprint, render_template, request
from flask_login import login_required
from auth import admin_required
from db import get_db

members_bp = Blueprint("members", __name__)

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