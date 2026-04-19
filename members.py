from flask import Blueprint, request, render_template, redirect, send_file
from db import get_db
import uuid
import os
import qrcode
from PIL import Image, ImageDraw

members_bp = Blueprint("members", __name__)

# ======================
# REGISTER
# ======================
@members_bp.route("/register", methods=["GET","POST"])
def register():

    if request.method == "GET":
        return render_template("register.html")

    data = request.form

    member_id = str(uuid.uuid4())[:8].upper()

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO members
        (membership_id, full_name, province, constituency, phone, status)
        VALUES (%s,%s,%s,%s,%s,'Active')
    """, (
        member_id,
        data.get("full_name"),
        data.get("province"),
        data.get("constituency"),
        data.get("phone")
    ))

    conn.commit()
    cur.close()
    conn.close()

    generate_assets(member_id)

    return redirect(f"/download_card/{member_id}")

# ======================
# CARD
# ======================
def generate_assets(member_id):

    os.makedirs("cards", exist_ok=True)

    path = f"cards/{member_id}.png"

    img = Image.new("RGB", (500,300), "#0B5D1E")
    draw = ImageDraw.Draw(img)

    draw.text((20,20), "PF PAMODZI ALLIANCE", fill="white")
    draw.text((20,100), f"ID: {member_id}", fill="gold")

    img.save(path)

# ======================
# DOWNLOAD
# ======================
@members_bp.route("/download_card/<member_id>")
def download(member_id):
    path = f"cards/{member_id}.png"

    if not os.path.exists(path):
        return "Not found", 404

    return send_file(path, as_attachment=True)

# ======================
# LIST
# ======================
@members_bp.route("/members")
def members():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT membership_id, full_name, phone, province, constituency, status
        FROM members
        ORDER BY full_name
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("members.html", members=rows)

# ======================
# DELETE
# ======================
@members_bp.route("/delete_member/<member_id>")
def delete(member_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM members WHERE membership_id=%s", (member_id,))
    conn.commit()

    cur.close()
    conn.close()

    return redirect("/members")
