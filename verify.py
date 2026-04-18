from flask import Blueprint, render_template, request, jsonify
from db import get_db

verify_bp = Blueprint("verify", __name__)

@verify_bp.route("/verify")
def verify_page():
    return render_template("verify.html")


@verify_bp.route("/api/verify_member", methods=["POST"])
def verify_member():

    data = request.get_json()
    member_id = data.get("member_id")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT full_name, province, constituency, status
        FROM members
        WHERE membership_id=%s
    """, (member_id,))

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return jsonify({"valid": False})

    return jsonify({
        "valid": True,
        "name": row[0],
        "province": row[1],
        "constituency": row[2],
        "status": row[3]
    })