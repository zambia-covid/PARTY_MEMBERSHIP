import os
import random
import qrcode
import psycopg2
import requests

from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, flash
from dotenv import load_dotenv
from datetime import date
from functools import wraps

from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)

from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

# ======================
# LOAD ENV
# ======================
load_dotenv()

# ======================
# APP INIT
# ======================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise ValueError("SECRET_KEY missing")

# ======================
# LOGIN SETUP
# ======================
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ======================
# USER MODEL
# ======================
class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return User("admin", "admin")
    if str(user_id).isdigit():
        return User(user_id, "agent")
    return None

# ======================
# ROLES
# ======================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            return "Forbidden", 403
        return f(*args, **kwargs)
    return wrapper

def agent_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "agent":
            return "Forbidden", 403
        return f(*args, **kwargs)
    return wrapper

# ======================
# DATABASE
# ======================
def get_db():
    db_url = os.getenv("DATABASE_URL")

    if db_url:
        return psycopg2.connect(db_url, sslmode="require")

    return psycopg2.connect(
        host="localhost",
        database="membership_db",
        user="postgres",
        password=os.getenv("DB_PASSWORD")
    )

# ======================
# MEMBER ID
# ======================
def generate_member_id():
    return f"PFP{random.randint(100000,999999)}"

# ======================
# QR + CARD
# ======================
def generate_qr(member_id):
    os.makedirs("qr", exist_ok=True)
    path = f"qr/{member_id}.png"
    qrcode.make(member_id).save(path)
    return path

def generate_card(name, province, constituency, member_id):
    os.makedirs("cards", exist_ok=True)
    path = f"cards/{member_id}.png"

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
# DOWNLOAD CARD
# ======================
@app.route("/download_card/<member_id>")
def download_card(member_id):
    path = f"cards/{member_id}.png"
    if not os.path.exists(path):
        return "Card not found", 404
    return send_file(path, as_attachment=True)

# ======================
# REGISTER
# ======================
@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "GET":
        return render_template("register.html")

    data = request.form

    name = data.get("full_name")
    province = data.get("province")
    constituency = data.get("constituency")
    phone = data.get("phone")

    member_id = generate_member_id()

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

    # generate assets
    generate_qr(member_id)
    generate_card(name, province, constituency, member_id)

    # 🔥 redirect to card
    return redirect(f"/download_card/{member_id}")

# ======================
# MEMBERS LIST
# ======================
@app.route("/members")
@login_required
@admin_required
def members():

    conn = get_db()
    cur = conn.cursor()

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

# ======================
# DELETE MEMBER
# ======================
@app.route("/delete_member/<member_id>")
@login_required
@admin_required
def delete_member(member_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM members WHERE membership_id=%s", (member_id,))
    conn.commit()

    cur.close()
    conn.close()

    return redirect("/members")

# ======================
# LOGIN
# ======================
users = {
    "admin": generate_password_hash(os.getenv("ADMIN_PASSWORD"))
}

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in users and check_password_hash(users[username], password):
            login_user(User(username, "admin"))
            return redirect("/")

        flash("Invalid credentials")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# ======================
# DASHBOARD
# ======================
@app.route("/")
@login_required
@admin_required
def dashboard():
    return render_template("dashboard.html")

# ======================
# RUN
# ======================
if __name__ == "__main__":
    app.run(debug=True)
