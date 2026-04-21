from flask import Blueprint, request, render_template, redirect, send_file
from db import get_db
import os
import random
import qrcode
from PIL import Image, ImageDraw

members_bp = Blueprint("members", __name__)

# ======================
# MEMBER ID
# ======================
def generate_member_id():
    return f"PFP{random.randint(100000,999999)}"


# ======================
# QR
# ======================
def generate_qr(member_id):
    os.makedirs("static/qr", exist_ok=True)
    path = f"static/qr/{member_id}.png"
    qrcode.make(member_id).save(path)
    return path


# ======================
# CARD
# ======================
def generate_card(name, province, constituency, member_id):

    os.makedirs("static/cards", exist_ok=True)
    path = f"static/cards/{member_id}.png"

    img = Image.new("RGB", (600, 300), "#0B5D1E")
    draw = ImageDraw.Draw(img)

    draw.text((20,20), "PF PAMODZI ALLIANCE", fill="white")
    draw.text((20,80), f"Name: {name}", fill="white")
    draw.text((20,120), f"Province: {province}", fill="white")
    draw.text((20,160), f"Constituency: {constituency}", fill="white")
    draw.text((20,200), f"ID: {member_id}", fill="gold")

    img.save(path)
    return path


# ======================
# REGISTER
# ======================
@members_bp.route("/register", methods=["GET","POST"])
def register():

    if request.method == "GET":
        return render_template("register.html")

    data = request.form

    member_id = generate_member_id()

    name = data.get("full_name")
    province = data.get("province")
    constituency = data.get("constituency")
    phone = data.get("phone")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO members
        (membership_id, full_name, province, constituency, phone, status)
        VALUES (%s,%s,%s,%s,%s,'Active')
    """, (member_id, name, province, constituency, phone))

    conn.commit()
    cur.close()
    conn.close()

    # 🔥 generate assets
    generate_qr(member_id)
    generate_card(name, province, constituency, member_id)

    return redirect(f"/download_card/{member_id}")


# ======================
# DOWNLOAD CARD
# ======================
@members_bp.route("/download_card/<member_id>")
def download(member_id):

    path = f"static/cards/{member_id}.png"

    if not os.path.exists(path):
        return "Card not found", 404

    return send_file(path, as_attachment=True)


# ======================
# MEMBERS LIST
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
# DELETE MEMBER
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
