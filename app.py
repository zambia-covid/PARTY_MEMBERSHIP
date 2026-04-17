import os
import random
import qrcode
import psycopg2
import requests
import threading

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, redirect, Response, session, url_for, send_file, flash
from twilio.rest import Client
from PIL import Image, ImageDraw, ImageFont
from datetime import date
from flask_login import login_user
from functools import wraps
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI

# ======================
# CREATE APP FIRST
# ======================
app = Flask(__name__)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is required")

app.secret_key = SECRET_KEY

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ======================
# LOGIN MANAGER
# ======================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ======================
# ADMIN
# ======================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            return "Forbidden", 403
        return f(*args, **kwargs)
    return wrapper
    
# ======================
# AI
# ======================
def ai_classify_voter(member):
    try:
        prompt = f"""
Classify this voter:

Name: {member.get("full_name")}
Province: {member.get("province")}
Constituency: {member.get("constituency")}
Ward: {member.get("ward")}

Return ONLY one word:
STRONG, LEANING, WEAK
"""

        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        return res.output_text.strip().upper()

    except Exception as e:
        print("AI classification error:", e)
        return "UNKNOWN"

# ======================
# AGENT
# ======================
def agent_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "agent":
            return "Forbidden", 403
        return f(*args, **kwargs)
    return wrapper

# ==============================
# SMS (TALKING AFRICA)
# ==============================

def send_sms(phone, message):
    url = "https://api.talkingafrica.com/v1/send_sms"

    payload = {
        "api_key": os.getenv("TA_API_KEY"),
        "username": os.getenv("TA_USERNAME"),
        "to": phone,
        "message": message,
        "sender_id": os.getenv("TA_SENDER_ID")  # e.g. "PF2026"
    }

    try:
        res = requests.post(url, json=payload, timeout=10)

        print(f"[SMS RESPONSE] {res.status_code} -> {res.text}")

        if not res.ok:
            print(f"[SMS ERROR] Failed for {phone}")

    except Exception as e:
        print(f"[SMS EXCEPTION] {phone}: {e}")

# ======================
# USER CLASS
# ======================
class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role

# ======================
# USER LOADER 
# ======================
@login_manager.user_loader
def load_user(user_id):

    # Admin
    if user_id == "admin":
        return User("admin", "admin")

    # Agent (numeric IDs)
    if str(user_id).isdigit():
        return User(user_id, "agent")

    return None

# ==============================
# ENVIRONMENT
# ==============================

ENV = os.getenv("ENV", "development")

app.config["SESSION_COOKIE_SECURE"] = ENV == "production"

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Missing BOT_TOKEN")

DATABASE_URL = os.getenv("DATABASE_URL")

users = {
    "admin": generate_password_hash(os.getenv("ADMIN_PASSWORD"))
}

# ==============================
# DATABASE CONNECTION
# ==============================

def get_db():
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        # LOCAL DEV ONLY
        return psycopg2.connect(
            host="localhost",
            database="membership_db",
            user="postgres",
            password=os.getenv("DB_PASSWORD")
        )

    # 🔴 RENDER / PRODUCTION
    return psycopg2.connect(
        db_url,
        sslmode="require"
    )

# ==============================
# CONSTITUENCY PENETRATION
# ==============================

def classify_constituency(penetration):
    if penetration >= 50:
        return "WIN"
    elif penetration >= 30:
        return "TOSS-UP"
    else:
        return "LOSE"

# ==============================
# TELEGRAM FUNCTIONS
# ==============================

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text
    }

    try:
        print(f"[TG] Sending to {chat_id}")

        res = requests.post(url, data=payload, timeout=10)

        print(f"[TG RESPONSE] {res.status_code} -> {res.text}")

        if not res.ok:
            print(f"[TG ERROR] Failed for {chat_id}")

    except Exception as e:
        print(f"[TG EXCEPTION] {chat_id}: {e}")


def send_photo(chat_id, photo):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    try:
        print(f"[TG PHOTO] Sending to {chat_id}")

        with open(photo, "rb") as img:
            res = requests.post(
                url,
                data={"chat_id": chat_id},
                files={"photo": img},
                timeout=10
            )

        print(f"[TG PHOTO RESPONSE] {res.status_code} -> {res.text}")

    except Exception as e:
        print(f"[TG PHOTO ERROR] {chat_id}: {e}")

# ==============================
# WHATSAPP FUNCTIONS
# ==============================

def send_whatsapp_message(phone, message):

    client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

    try:
        msg = client.messages.create(
            body=message,
            from_=os.getenv("TWILIO_WHATSAPP_NUMBER"),
            to=f"whatsapp:{phone}"
        )

        print(f"Sent to {phone} | SID: {msg.sid}")

    except Exception as e:
        print(f"Failed to send to {phone}: {e}")

# ==============================
# QR CODE
# ==============================

def generate_qr(member_id):
    os.makedirs("qr", exist_ok=True)
    path = f"qr/{member_id}.png"

    img = qrcode.make(member_id)
    img.save(path)

    return path


# ==============================
# MEMBER ID
# ==============================

def generate_member_id():
    conn = get_db()
    cur = conn.cursor()

    while True:
        number = random.randint(100000, 999999)
        member_id = f"PFP{number}"

        cur.execute("SELECT 1 FROM members WHERE membership_id=%s", (member_id,))
        if not cur.fetchone():
            break

    cur.close()
    conn.close()

    return member_id


# ==============================
# MEMBERSHIP CARD
# ==============================

import os
import qrcode
from PIL import Image, ImageDraw, ImageFont
from datetime import date

def generate_membership_card(name, province, constituency, member_id):
    issue_date = str(date.today())

    # ==============================
    # QR CODE
    # ==============================
    qr_data = f"""
Organisation: PF Pamodzi Alliance
Name: {name}
Province: {province}
Constituency: {constituency}
Membership ID: {member_id}
Issue Date: {issue_date}
"""
    qr = qrcode.make(qr_data).resize((180, 180))

    # ==============================
    # CARD BASE (GREEN THEME)
    # ==============================
    width, height = 700, 400
    card = Image.new("RGB", (width, height), "#0B5D1E")  # deep green
    draw = ImageDraw.Draw(card)

    # ==============================
    # FONTS
    # ==============================
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 28)
        text_font = ImageFont.truetype("arial.ttf", 18)
        small_font = ImageFont.truetype("arial.ttf", 14)
    except:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # ==============================
    # HEADER BAR
    # ==============================
    draw.rectangle([(0, 0), (width, 70)], fill="#083D14")  # darker green
    draw.text((20, 20), "PF PAMODZI ALLIANCE", fill="white", font=title_font)

    # ==============================
    # MEMBER DETAILS
    # ==============================
    y_start = 100
    line_gap = 35

    draw.text((30, y_start), f"Full Name:", fill="#C8E6C9", font=text_font)
    draw.text((180, y_start), name, fill="white", font=text_font)

    draw.text((30, y_start + line_gap), "Province:", fill="#C8E6C9", font=text_font)
    draw.text((180, y_start + line_gap), province, fill="white", font=text_font)

    draw.text((30, y_start + 2*line_gap), "Constituency:", fill="#C8E6C9", font=text_font)
    draw.text((180, y_start + 2*line_gap), constituency, fill="white", font=text_font)

    draw.text((30, y_start + 3*line_gap), "Membership ID:", fill="#C8E6C9", font=text_font)
    draw.text((180, y_start + 3*line_gap), member_id, fill="#FFD700", font=text_font)  # gold highlight

    draw.text((30, y_start + 4*line_gap), "Issue Date:", fill="#C8E6C9", font=small_font)
    draw.text((180, y_start + 4*line_gap), issue_date, fill="white", font=small_font)

    # ==============================
    # QR SECTION
    # ==============================
    qr_x, qr_y = 480, 110

    # white box behind QR for contrast
    draw.rectangle(
        [(qr_x - 10, qr_y - 10), (qr_x + 190, qr_y + 190)],
        fill="white"
    )

    card.paste(qr, (qr_x, qr_y))

    draw.text((qr_x, qr_y + 200), "Scan to verify", fill="white", font=small_font)

    # ==============================
    # FOOTER STRIP
    # ==============================
    draw.rectangle([(0, height - 40), (width, height)], fill="#083D14")
    draw.text((20, height - 30), "Official Membership Card", fill="white", font=small_font)

    # ==============================
    # SAVE
    # ==============================
    os.makedirs("cards", exist_ok=True)
    path = f"cards/{member_id}.png"
    card.save(path)

    return path

# ==============================
# TELEGRAM STATE STORAGE
# ==============================

telegram_states = {}
telegram_data = {}

# ==============================
# WHATSAPP STATE STORAGE
# ==============================

whatsapp_states = {}
whatsapp_data = {}

# ==============================
# POLLING STATION ASSIGNMENT
# ==============================

def assign_polling_station(member):
    """
    Assigns a polling station to a member based on their province, district, and constituency.
    Uses the station with the least number of members assigned.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT ps.polling_station, COUNT(m.membership_id) AS current_count
        FROM polling_stations ps
        LEFT JOIN members m
        ON m.polling_station = ps.polling_station
        WHERE ps.province=%s AND ps.district=%s AND ps.constituency=%s
        GROUP BY ps.polling_station
        ORDER BY current_count ASC
    """, (member["province"], member["district"], member["constituency"]))

    stations = cur.fetchall()
    cur.close()
    conn.close()

    if not stations:
        return "Not Assigned"

    # Assign the station with the least members
    return stations[0][0]

# ==============================
# GENERATE ASSET
# ==============================

def generate_assets_async(name, province, constituency, member_id):
    try:
        qr = generate_qr(member_id)
        card = generate_membership_card(name, province, constituency, member_id)
        print(f"[ASYNC] Generated assets for {member_id}")
    except Exception as e:
        print(f"[ASYNC ERROR] {e}")
# ==============================
# AI GENERATED MSG
# ==============================

def ai_generate_message(context):
    try:
        prompt = f"""
Create a short, powerful political campaign message.

Province: {context.get("province")}
Constituency: {context.get("constituency")}
Ward: {context.get("ward")}

Tone: persuasive, urgent, pro-development.
Under 40 words.
"""

        res = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        return res.output_text.strip()

    except Exception as e:
        print("AI message error:", e)
        return "Stay engaged. Your vote matters."

# ==============================
# SEND MULTI CHANNELS
# ==============================

def send_multi_channel(phone, chat_id, message):
    whatsapp = 0
    telegram = 0
    sms = 0

    # WhatsApp + SMS
    if phone:
        try:
            send_whatsapp_message(phone, message)
            send_sms(phone, message)
            whatsapp += 1
            sms += 1
        except Exception as e:
            print(f"[WA/SMS ERROR] {phone}: {e}")

    # Telegram
    if chat_id:
        try:
            send_telegram_message(chat_id, message)
            telegram += 1
        except Exception as e:
            print(f"[TG ERROR] {chat_id}: {e}")

    return whatsapp, telegram, sms
    
# ==============================
# VOTER SCORE
# ==============================

def calculate_voter_score(member):
    score = 0

    if member["province"] in ["Lusaka", "Copperbelt"]:
        score += 2  # strategic regions

    if member.get("chat_id"):
        score += 2  # reachable via Telegram

    if member.get("phone"):
        score += 2  # reachable via WhatsApp

    return score

def categorize_voter(score):
    if score >= 5:
        return "STRONG"
    elif score >= 3:
        return "LEANING"
    else:
        return "WEAK"

# ==============================
# INPUT VALIDATION
# ==============================

import re

def validate_name(name):
    if not name:
        raise ValueError("Name is required")
    name = name.strip()
    if not re.match(r"^[A-Za-z\s'-]{2,50}$", name):
        raise ValueError("Invalid name format")
    return name


def validate_location(value, field):
    if not value:
        raise ValueError(f"{field.capitalize()} is required")

    value = value.strip()

    if len(value) < 2:
        raise ValueError(f"Invalid {field}")

    return value


def normalize_phone(phone):
    if not phone:
        raise ValueError("Phone number is required")

    phone = phone.strip()

    if phone.startswith("0"):
        phone = "+260" + phone[1:]

    if not phone.startswith("+260") or len(phone) < 12:
        raise ValueError("Invalid Zambian phone number")

    return phone

@app.route("/download_card/<member_id>")
def download_card(member_id):
    path = f"cards/{member_id}.png"

    if not os.path.exists(path):
        return "Card not found", 404

    return send_file(path, as_attachment=True)

# ==============================
# AI INSIGHTS
# ==============================
@app.route("/ai_insights")
@login_required
@admin_required
def ai_insights():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT ai_support, COUNT(*)
        FROM members
        GROUP BY ai_support
    """)

    data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("ai_insights.html", data=data)

# ==============================
# REGISTER
# ==============================

@app.route('/register', methods=['GET', 'POST'])
def register():

    # =========================
    # SHOW FORM
    # =========================
    if request.method == "GET":
        return render_template("register.html")

    # =========================
    # HANDLE INPUT
    # =========================
    data = request.get_json() if request.is_json else request.form

    try:
        full_name = validate_name(data.get("full_name"))
        province = validate_location(data.get("province"), "province")
        district = validate_location(data.get("district"), "district")
        constituency = validate_location(data.get("constituency"), "constituency")
        ward = validate_location(data.get("ward"), "ward")
        phone = normalize_phone(data.get("phone"))

    except ValueError as e:
        return str(e), 400

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor()

        # =========================
        # CHECK EXISTING MEMBER
        # =========================
        cur.execute(
            "SELECT membership_id FROM members WHERE phone=%s",
            (phone,)
        )
        existing = cur.fetchone()

        if existing:
            member_id = existing[0]
            card_url = f"/download_card/{member_id}"

            return render_template(
                "success.html",
                member_id=member_id,
                card_url=card_url,
                message="You are already registered"
            )

        # =========================
        # GENERATE MEMBER ID
        # =========================
        member_id = generate_member_id()
        card_url = f"/download_card/{member_id}"

        # =========================
        # ASSIGN POLLING STATION
        # =========================
        polling_station = assign_polling_station({
            "province": province,
            "district": district,
            "constituency": constituency
        })

        # =========================
        # AI CLASSIFICATION
        # =========================
        ai_score = ai_classify_voter({
            "full_name": full_name,
            "province": province,
            "constituency": constituency,
            "ward": ward
        })

        # =========================
        # INSERT MEMBER
        # =========================
        cur.execute("""
            INSERT INTO members
            (membership_id, full_name, province, district, constituency, ward, phone, polling_station, status, ai_support)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Active',%s)
        """, (
            member_id,
            full_name,
            province,
            district,
            constituency,
            ward,
            phone,
            polling_station,
            ai_score
        ))

        conn.commit()

    except Exception as e:
        if conn:
            conn.rollback()
        return f"Error: {str(e)}", 500

    finally:
        if conn:
            conn.close()

    # =========================
    # GENERATE ASSETS (SAFE MODE)
    # =========================
    try:
        generate_assets_async(full_name, province, constituency, member_id)
    except Exception as e:
        print(f"[ASSET ERROR] {e}")

    # =========================
    # RESPONSE
    # =========================
    return render_template(
        "success.html",
        member_id=member_id,
        card_url=card_url,
        message="Registration successful. Your card is ready."
    )


# ==============================
# TELEGRAM WEBHOOK
# ==============================

@app.route("/telegram", methods=["GET", "POST"])
@app.route("/telegram/", methods=["GET", "POST"])
def telegram_webhook():

    if request.method == "GET":
        return "Telegram webhook active", 200

    try:
        data = request.get_json()

        if not data:
            return jsonify({"status": "no data"})

        message = data.get("message")
        if not message:
            return jsonify({"status": "ignored"})

        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()

        state = telegram_states.get(chat_id)

        # ======================
        # START
        # ======================
        if text == "/start":
            telegram_states[chat_id] = "ASK_NAME"
            telegram_data[chat_id] = {}

            send_telegram_message(chat_id, "Welcome. What is your full name?")
            return jsonify({"status": "ok"})

        # ======================
        # NAME
        # ======================
        if state == "ASK_NAME":
            telegram_data[chat_id]["name"] = text
            telegram_states[chat_id] = "ASK_PROVINCE"

            send_telegram_message(chat_id, "Which province?")
            return jsonify({"status": "ok"})

        # ======================
        # PROVINCE
        # ======================
        if state == "ASK_PROVINCE":
            telegram_data[chat_id]["province"] = text
            telegram_states[chat_id] = "ASK_DISTRICT"

            send_telegram_message(chat_id, "Which district?")
            return jsonify({"status": "ok"})

        # ======================
        # DISTRICT
        # ======================
        if state == "ASK_DISTRICT":
            telegram_data[chat_id]["district"] = text
            telegram_states[chat_id] = "ASK_CONSTITUENCY"

            send_telegram_message(chat_id, "Which constituency?")
            return jsonify({"status": "ok"})

        # ======================
        # CONSTITUENCY
        # ======================
        if state == "ASK_CONSTITUENCY":
            telegram_data[chat_id]["constituency"] = text
            telegram_states[chat_id] = "ASK_PHONE"

            send_telegram_message(chat_id, "Enter your phone number (e.g. +260XXXXXXXXX)")
            return jsonify({"status": "ok"})

        # ======================
        # PHONE → MOVE TO WARD
        # ======================
        if state == "ASK_PHONE":
            telegram_data[chat_id]["phone"] = text
            telegram_states[chat_id] = "ASK_WARD"

            send_telegram_message(chat_id, "Which ward?")
            return jsonify({"status": "ok"})

        # ======================
        # WARD (FINAL STEP)
        # ======================
        if state == "ASK_WARD":

            name = telegram_data[chat_id]["name"]
            province = telegram_data[chat_id]["province"]
            district = telegram_data[chat_id]["district"]
            constituency = telegram_data[chat_id]["constituency"]
            phone = telegram_data[chat_id]["phone"]
            ward = text

            conn = get_db()
            cur = conn.cursor()

            # CHECK IF USER EXISTS
            cur.execute("SELECT membership_id FROM members WHERE phone=%s", (phone,))
            existing = cur.fetchone()

            if existing:
                # UPDATE EXISTING USER
                cur.execute("""
                    UPDATE members
                    SET chat_id=%s, ward=%s
                    WHERE phone=%s
                """, (chat_id, ward, phone))

                conn.commit()

                send_telegram_message(chat_id, "You are already registered. Telegram linked and ward updated.")

            else:
                member_id = generate_member_id()

                cur.execute("""
                    INSERT INTO members
                    (membership_id, full_name, province, district, constituency, ward, phone, chat_id, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Active')
                """, (
                    member_id, name, province, district, constituency, ward, phone, chat_id
                ))

                conn.commit()

                send_telegram_message(chat_id, f"Registration complete\nMembership ID: {member_id}")

                qr = generate_qr(member_id)
                send_photo(chat_id, qr)

                card_path = generate_membership_card(name, province, constituency, member_id)
                send_photo(chat_id, card_path)

            cur.close()
            conn.close()

            # CLEAN STATE
            telegram_states.pop(chat_id, None)
            telegram_data.pop(chat_id, None)

            return jsonify({"status": "ok"})

        # ======================
        # FALLBACK
        # ======================
        send_telegram_message(chat_id, "Invalid input. Type /start to begin.")
        return jsonify({"status": "ok"})

    except Exception as e:
        print("Webhook error:", e)
        return jsonify({"error": "internal error"}), 500

# ==============================
# WHATSAPP
# ==============================
from twilio.twiml.messaging_response import MessagingResponse

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():

    msg = request.form.get("Body")
    phone_id = request.form.get("From")

    resp = MessagingResponse()

    state = whatsapp_states.get(phone_id)

    if msg.lower() == "start":

        whatsapp_states[phone_id] = "ASK_NAME"
        resp.message("Welcome to PF Pamodzi registration.\nWhat is your full name?")

        return str(resp)

    if state == "ASK_NAME":

        whatsapp_data[phone_id] = {"name": msg}
        whatsapp_states[phone_id] = "ASK_PROVINCE"

        resp.message("Which province?")
        return str(resp)

    if state == "ASK_PROVINCE":

        whatsapp_data[phone_id]["province"] = msg
        whatsapp_states[phone_id] = "ASK_DISTRICT"

        resp.message("Which district?")
        return str(resp)

    if state == "ASK_DISTRICT":

        whatsapp_data[phone_id]["district"] = msg
        whatsapp_states[phone_id] = "ASK_CONSTITUENCY"

        resp.message("Which constituency?")
        return str(resp)

    if state == "ASK_CONSTITUENCY":

        whatsapp_data[phone_id]["constituency"] = msg
        whatsapp_states[phone_id] = "ASK_PHONE"

        resp.message("Enter your phone number")
        return str(resp)

    if state == "ASK_PHONE":

        name = whatsapp_data[phone_id]["name"]
        province = whatsapp_data[phone_id]["province"]
        district = whatsapp_data[phone_id]["district"]
        constituency = whatsapp_data[phone_id]["constituency"]
        phone = msg

        conn = get_db()
        cur = conn.cursor()

        member_id = generate_member_id()

        polling_station = assign_polling_station({
            "membership_id": member_id,
            "province": province,
            "district": district,
            "constituency": constituency
        })

        cur.execute("""
            INSERT INTO members
            (membership_id, full_name, province, district, constituency, phone, polling_station, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'Active')
        """, (
            member_id,
            name,
            province,
            district,
            constituency,
            phone,
            polling_station
        ))

        conn.commit()

        resp.message(
            f"Registration complete\nMembership ID: {member_id}\nPolling Station: {polling_station}"
        )

        whatsapp_states.pop(phone_id, None)
        whatsapp_data.pop(phone_id, None)

        return str(resp)

# ==============================
# CONSTITUENCY DETAIL
# ==============================

@app.route("/constituency_detail/<constituency>")
@login_required
def constituency_detail(constituency):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT polling_station,
               pf_votes,
               upnd_votes
        FROM polling_station_results
        WHERE constituency = %s
    """, (constituency,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            "station": r[0],
            "pf": r[1],
            "upnd": r[2]
        } for r in rows
    ])

@app.route("/approve/<int:id>", methods=['POST'])
@login_required
@admin_required
def approve(id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("UPDATE applicants SET status='Approved' WHERE id=%s", (id,))
    conn.commit()

    cur.close()
    conn.close()

    return '', 204

@app.route("/reject/<int:id>", methods=['POST'])
@login_required
@admin_required
def reject(id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("UPDATE applicants SET status='Rejected' WHERE id=%s", (id,))
    conn.commit()

    cur.close()
    conn.close()

    return '', 204

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in users and check_password_hash(users[username], password):
            user = User(username, "admin")
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid credentials")
        return redirect("/login")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")
    
# ==============================
# CONSTITUENCY INTELLIGENCE
# ==============================
@app.route("/api/constituency_intelligence")
@login_required
def api_constituency_intelligence():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            c.constituency,
            c.province,

            COUNT(DISTINCT m.membership_id) AS members,
            c.total_voters,
            c.total_polling_stations,

            COALESCE(SUM(r.pf_votes), 0) AS pf_votes,
            COALESCE(SUM(r.upnd_votes), 0) AS upnd_votes

        FROM constituencies c

        LEFT JOIN members m
            ON m.constituency = c.constituency
            AND m.status = 'Active'

        LEFT JOIN polling_station_results r
            ON r.constituency = c.constituency

        GROUP BY 
            c.constituency,
            c.province,
            c.total_voters,
            c.total_polling_stations
    """)

    rows = cur.fetchall()

    results = []

    for r in rows:

        constituency, province, members, voters, stations, pf, upnd = r

        penetration = (members / voters * 100) if voters else 0
        margin = pf - upnd

        if margin > 0 and penetration >= 40:
            status = "WIN"
        elif margin < 0 and penetration < 30:
            status = "LOSE"
        else:
            status = "TOSS-UP"

        results.append({
            "constituency": constituency,
            "province": province,
            "members": members,
            "voters": voters,
            "stations": stations,
            "pf_votes": pf,
            "upnd_votes": upnd,
            "penetration": round(penetration, 2),
            "margin": margin,
            "status": status
        })

    cur.close()
    conn.close()

    return jsonify(results)

# ==============================
# FAVICON
# ==============================
@app.route('/favicon.ico')
def favicon():
    return send_file('static/favicon.ico')

@app.route("/ai")
@login_required
def ai_page():
    return render_template("ai.html")

# ==============================
# AGENT REPORT
# ==============================

@app.route('/submit_results', methods=['GET', 'POST'])
@login_required
@agent_required
def submit_results():

    if request.method == 'POST':

        pf = int(request.form.get("pf", 0))
        upnd = int(request.form.get("upnd", 0))
        other = int(request.form.get("other", 0))

        agent_id = current_user.id.replace("agent_", "")

        conn = get_db()
        cur = conn.cursor()

        # Get agent details
        cur.execute("""
            SELECT province, constituency, polling_station
            FROM agents
            WHERE agent_id=%s
        """, (agent_id,))
        agent = cur.fetchone()

        if not agent:
            return "Agent not found", 404

        province, constituency, polling_station = agent

        # 🔴 INSERT INTO REAL TABULATION TABLE
        cur.execute("""
            INSERT INTO polling_station_results
            (agent_id, province, constituency, polling_station, pf_votes, upnd_votes, other_votes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (agent_id, province, constituency, polling_station, pf, upnd, other))

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for('agent_dashboard'))

    return render_template('submit_results.html')

@app.route('/request_help', methods=['GET', 'POST'])
@login_required
@agent_required
def request_help():

    if request.method == 'POST':

        message = request.form.get("message")
        agent_id = current_user.id.replace("agent_", "")

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT province, constituency, polling_station
            FROM agents
            WHERE agent_id=%s
        """, (agent_id,))
        agent = cur.fetchone()

        province, constituency, polling_station = agent

        # Save request
        cur.execute("""
            INSERT INTO incidents
            (agent_id, province, constituency, polling_station, message)
            VALUES (%s, %s, %s, %s, %s)
        """, (agent_id, province, constituency, polling_station, f"HELP: {message}"))

        conn.commit()

        # 🔥 OPTIONAL: Alert admin instantly
        send_whatsapp_message(
            os.getenv("ADMIN_PHONE"),
            f"🚨 HELP REQUEST\nStation: {polling_station}\n{message}"
        )

        cur.close()
        conn.close()

        return redirect(url_for('agent_dashboard'))

    return render_template('request_help.html')


@app.route("/incidents")
@login_required
def incidents_page():
    return render_template("incidents.html")

@app.route('/report_incident', methods=['GET', 'POST'])
@login_required
@agent_required
def report_incident():

    if request.method == 'POST':

        message = request.form.get("incident")

        if not message:
            return "Incident message required", 400

        agent_id = current_user.id.replace("agent_", "")

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT province, constituency, polling_station
            FROM agents
            WHERE agent_id=%s
        """, (agent_id,))

        agent = cur.fetchone()

        if not agent:
            cur.close()
            conn.close()
            return "Agent not found", 404

        province, constituency, polling_station = agent

        cur.execute("""
            INSERT INTO incidents
            (agent_id, province, constituency, polling_station, message)
            VALUES (%s, %s, %s, %s, %s)
        """, (agent_id, province, constituency, polling_station, message))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(url_for('agent_dashboard'))

    return render_template('report_incident.html')

# ==============================
# VOTE TABULATION
# ==============================

@app.route("/voter_tabulation")
@login_required
def voter_tabulation():

    conn = get_db()
    cur = conn.cursor()

    # 🔢 Aggregate totals per polling station
    cur.execute("""
        SELECT 
            polling_station,
            SUM(pf_votes) as pf,
            SUM(upnd_votes) as upnd,
            SUM(other_votes) as other
        FROM polling_station_results
        GROUP BY polling_station
        ORDER BY polling_station
    """)

    results = cur.fetchall()

    # 🔢 National totals
    cur.execute("""
        SELECT 
            COALESCE(SUM(pf_votes),0),
            COALESCE(SUM(upnd_votes),0),
            COALESCE(SUM(other_votes),0)
        FROM polling_station_results
    """)

    totals = cur.fetchone()

    cur.close()
    conn.close()

    return render_template(
        "voter_tabulation.html",
        results=results,
        totals=totals
    )

# ==============================
# AGENT VOTE SEND
# ==============================
@app.route("/agent_results")
@login_required
def agent_results():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT agent_id, province, constituency, polling_station,
               pf_votes, upnd_votes, other_votes
        FROM polling_station_results
        ORDER BY polling_station
    """)

    results = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("agent_results.html", results=results)

# ==============================
# API ACCIDENTS
# ==============================
@app.route("/api/incidents")
@login_required
def api_incidents():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            id,
            agent_id,
            province,
            constituency,
            polling_station,
            message,
            created_at
        FROM incidents
        ORDER BY created_at DESC
        LIMIT 100
    """)

    rows = cur.fetchall()

    incidents = []

    for r in rows:
        incidents.append({
            "id": r[0],
            "agent_id": r[1],
            "province": r[2],
            "constituency": r[3],
            "polling_station": r[4],
            "message": r[5],
            "created_at": str(r[6]) if r[6] else None
        })

    cur.close()
    conn.close()

    return jsonify(incidents)

# ==============================
# AGENT VOTE SEND
# ==============================

def send_votes_for_constituency(constituency):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT phone FROM members WHERE constituency=%s AND status='Active'", (constituency,))
    phones = [row[0] for row in cur.fetchall()]

    for p in phones:
        send_whatsapp_message(p, f"Voting instructions for {constituency}...")

    cur.close()
    conn.close()
    return len(phones)

@app.route("/agent_vote_send", methods=["POST"])
@login_required
@agent_required
def agent_vote_send():
    incoming_msg = request.form.get("Body")
    sender = request.form.get("From")

    if not incoming_msg:
        return jsonify({"reply": "No message received"})

    msg = incoming_msg.strip().upper()

    conn = get_db()
    cur = conn.cursor()

    # ==============================
    # VERIFY AGENT
    # ==============================
    cur.execute("""
        SELECT agent_id, province, constituency, polling_station
        FROM agents
        WHERE phone=%s AND active=TRUE
    """, (sender,))
    agent = cur.fetchone()

    if not agent:
        return jsonify({"reply": "Unauthorized agent."})

    agent_id, province, constituency, polling_station = agent

    # ==============================
    # COMMAND HANDLER
    # ==============================

    # 🔹 RESULT
    if msg.startswith("RESULT"):
        try:
            parts = msg.split()

            pf_votes = int(parts[1])
            upnd_votes = int(parts[2])
            other_votes = int(parts[3]) if len(parts) > 3 else 0

            cur.execute("""
                INSERT INTO polling_station_results
                (agent_id, province, constituency, polling_station, pf_votes, upnd_votes, other_votes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (agent_id, province, constituency, polling_station, pf_votes, upnd_votes, other_votes))

            conn.commit()

            reply = f"Results received for {polling_station}. PF:{pf_votes} UPND:{upnd_votes}"

        except:
            reply = "Invalid format. Use: RESULT PF UPND OTHER"

    # 🔹 TURNOUT
    elif msg == "TURNOUT":

        cur.execute("""
            SELECT COUNT(*) FROM members
            WHERE polling_station=%s
        """, (polling_station,))
        total_members = cur.fetchone()[0]

        cur.execute("""
            SELECT COALESCE(SUM(pf_votes + upnd_votes + other_votes),0)
            FROM polling_station_results
            WHERE polling_station=%s
        """, (polling_station,))
        total_votes = cur.fetchone()[0]

        gap = total_members - total_votes

        reply = (
            f"📊 TURNOUT\n"
            f"Station: {polling_station}\n"
            f"Members: {total_members}\n"
            f"Votes: {total_votes}\n"
            f"Gap: {gap}"
        )

    # 🔹 HELP (REINFORCEMENT)
    elif msg == "HELP":

        admin_phone = os.getenv("ADMIN_PHONE")

        # Alert HQ
        send_whatsapp_message(
            admin_phone,
            f"🚨 HELP REQUEST\nStation: {polling_station}\nConstituency: {constituency}"
        )

        # Notify supporters at same station
        cur.execute("""
            SELECT phone FROM members
            WHERE polling_station=%s AND status='Active'
        """, (polling_station,))

        supporters = cur.fetchall()

        count = 0
        for s in supporters:
            try:
                send_whatsapp_message(
                    s[0],
                    f"⚠️ URGENT: Go vote now at {polling_station}"
                )
                count += 1
            except:
                pass

        reply = f"Reinforcement sent to {count} supporters."

    # 🔹 ALERT (INCIDENT)
    elif msg.startswith("ALERT"):

        incident_msg = incoming_msg.replace("ALERT", "").strip()

        if not incident_msg:
            reply = "Use: ALERT <message>"
        else:
            cur.execute("""
                INSERT INTO incidents
                (agent_id, province, constituency, polling_station, message)
                VALUES (%s, %s, %s, %s, %s)
            """, (agent_id, province, constituency, polling_station, incident_msg))

            conn.commit()

            admin_phone = os.getenv("ADMIN_PHONE")

            send_whatsapp_message(
                admin_phone,
                f"🚨 INCIDENT\n{polling_station}\n{incident_msg}"
            )

            reply = "Incident reported."

    # 🔹 SEND VOTES (existing)
    elif msg == "SEND VOTES":
        recipients = send_votes_for_constituency(constituency)
        reply = f"Broadcast sent to {recipients} members."

    # 🔹 UNKNOWN
    else:
        reply = "Use: RESULT, TURNOUT, HELP, ALERT"

    cur.close()
    conn.close()

    return jsonify({"reply": reply})

# ==============================
# BROADCAST
# ==============================

@app.route('/broadcast', methods=['POST'])
@login_required
def broadcast():

    # ==============================
    # INPUT HANDLING
    # ==============================
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    message = data.get("message")

    # 🎯 DIRECT TARGETING
    chat_id = data.get("chat_id")
    phone = data.get("phone")

    # 📡 FILTER TARGETING
    province = data.get("province")
    district = data.get("district")
    constituency = data.get("constituency")
    ward = data.get("ward")

    # ==============================
    # 🤖 AI MESSAGE OVERRIDE
    # ==============================
    use_ai = str(data.get("use_ai")).lower() == "true"

    if use_ai:
        message = ai_generate_message({
            "province": province,
            "constituency": constituency,
            "ward": ward
        })

    # ==============================
    # VALIDATION
    # ==============================
    if not message:
        return jsonify({"error": "Message is required"}), 400

    # ==============================
    # COUNTERS
    # ==============================
    whatsapp_sent = 0
    telegram_sent = 0
    sms_sent = 0

    import time

    # ==========================================
    # 🎯 DIRECT MESSAGE MODE
    # ==========================================
    if chat_id or phone:

        wa, tg, sms = send_multi_channel(phone, chat_id, message)

        whatsapp_sent += wa
        telegram_sent += tg
        sms_sent += sms

        return jsonify({
            "status": "direct_sent",
            "whatsapp_sent": whatsapp_sent,
            "telegram_sent": telegram_sent,
            "sms_sent": sms_sent,
            "chat_id": chat_id,
            "phone": phone,
            "message_used": message
        }), 200

    # ==========================================
    # 📡 BROADCAST MODE
    # ==========================================
    conn = get_db()
    cur = conn.cursor()

    query = "SELECT phone, chat_id FROM members WHERE status='Active'"
    params = []

    if province:
        query += " AND province=%s"
        params.append(province)

    if district:
        query += " AND district=%s"
        params.append(district)

    if constituency:
        query += " AND constituency=%s"
        params.append(constituency)

    if ward:
        query += " AND ward=%s"
        params.append(ward)

    cur.execute(query, params)
    rows = cur.fetchall()

    for phone, chat_id in rows:

        wa, tg, sms = send_multi_channel(phone, chat_id, message)

        whatsapp_sent += wa
        telegram_sent += tg
        sms_sent += sms

        time.sleep(0.1)

    cur.close()
    conn.close()

    return jsonify({
        "status": "broadcast_sent",
        "whatsapp_sent": whatsapp_sent,
        "telegram_sent": telegram_sent,
        "sms_sent": sms_sent,
        "total_targeted": len(rows),
        "message_used": message
    }), 200
    
# ==============================
# LIVE STATS
# ==============================

@app.route("/live_stats")
@login_required
def live_stats():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT 
        cs.constituency,
        cs.province,

        COUNT(DISTINCT m.membership_id) AS members,
        cs.total_voters,
        cs.total_polling_stations,

        COALESCE(SUM(r.pf_votes), 0) AS pf_votes,
        COALESCE(SUM(r.upnd_votes), 0) AS upnd_votes

    FROM constituency_stats cs

    LEFT JOIN members m
        ON m.constituency = cs.constituency
        AND m.status = 'Active'

    LEFT JOIN polling_station_results r
        ON r.constituency = cs.constituency

    GROUP BY cs.constituency, cs.province, cs.total_voters, cs.total_polling_stations
    """)

    rows = cur.fetchall()

    results = []

    for r in rows:
        constituency, province, members, voters, stations, pf, upnd = r

        # 🔴 CORE INTELLIGENCE
        penetration = (members / voters * 100) if voters > 0 else 0
        expected_votes = int(members * 0.65)
        margin = pf - upnd

        # 🔴 FINAL STATUS (REALITY-BASED)
        if pf > upnd and penetration >= 40:
            status = "WIN"
        elif pf < upnd and penetration < 30:
            status = "LOSE"
        else:
            status = "TOSS-UP"

        results.append({
            "constituency": constituency,
            "province": province,
            "members": members,
            "voters": voters,
            "stations": stations,
            "pf_votes": pf,
            "upnd_votes": upnd,
            "expected_votes": expected_votes,
            "penetration": round(penetration, 2),
            "margin": margin,
            "status": status
        })

    cur.close()
    conn.close()

    return jsonify(results)

# ==============================
# AGENT LOGIN
# ==============================

@app.route("/agent_login", methods=["GET", "POST"])
def agent_login():

    if request.method == "POST":
        phone = request.form["phone"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT agent_id, password
            FROM agents
            WHERE phone=%s AND active=TRUE
        """, (phone,))

        agent = cur.fetchone()

        cur.close()
        conn.close()

        # 🔴 CRITICAL FIX: handle NULL password safely
        if agent and agent[1] and check_password_hash(agent[1], password):

            user = User(str(agent[0]), "agent")
            login_user(user)

            return redirect("/agent_dashboard")

        return render_template("agent_login.html", error="Invalid credentials")

    return render_template("agent_login.html")

@app.route("/agent_dashboard")
@login_required
@agent_required
def agent_dashboard():

    agent_id = current_user.id.replace("agent_", "")

    conn = get_db()
    cur = conn.cursor()

    # Agent info
    cur.execute("""
        SELECT name, province, constituency, polling_station
        FROM agents
        WHERE agent_id=%s
    """, (agent_id,))
    agent = cur.fetchone()

    # Latest result
    cur.execute("""
        SELECT pf_votes, upnd_votes, other_votes
        FROM polling_station_results
        WHERE agent_id=%s
        ORDER BY id DESC
        LIMIT 1
    """, (agent_id,))
    result = cur.fetchone()

    # Incidents
    cur.execute("""
        SELECT message
        FROM incidents
        WHERE agent_id=%s
        ORDER BY id DESC
        LIMIT 5
    """, (agent_id,))
    incidents = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "agent_dashboard.html",
        agent=agent,
        result=result,
        incidents=incidents
    )

# ==============================
# WAR ROOM
# ==============================
@app.route("/war_room")
@login_required
@admin_required
def war_room():

    conn = get_db()
    cur = conn.cursor()

    # ==============================
    # CONSTITUENCY STATUS
    # ==============================
    cur.execute("""
    SELECT 
        cs.constituency,
        cs.province,

        -- MEMBERS
        COUNT(DISTINCT m.membership_id) AS members,

        -- NATIONAL BASELINE
        cs.total_voters,
        cs.total_polling_stations,

        -- REAL VOTES
        COALESCE(SUM(r.pf_votes), 0) AS pf_votes,
        COALESCE(SUM(r.upnd_votes), 0) AS upnd_votes

    FROM constituency_stats cs

    LEFT JOIN members m
        ON m.constituency = cs.constituency
        AND m.status = 'Active'

    LEFT JOIN polling_station_results r
        ON r.constituency = cs.constituency

    GROUP BY cs.constituency, cs.province, cs.total_voters, cs.total_polling_stations
""")

    battleground = []
    for c, pf, upnd in cur.fetchall():

        if pf > upnd:
            status = "WIN"
        elif pf < upnd:
            status = "LOSE"
        else:
            status = "TIE"

        battleground.append((c, pf, upnd, status))

    # ==============================
    # SILENT STATIONS
    # ==============================
    cur.execute("""
        SELECT a.polling_station
        FROM agents a
        LEFT JOIN polling_station_results r
        ON a.polling_station = r.polling_station
        WHERE r.id IS NULL
    """)

    silent_stations = [row[0] for row in cur.fetchall()]

    # ==============================
    # TOP ALERT ZONES (LOSING BADLY)
    # ==============================
    cur.execute("""
        SELECT constituency,
               SUM(upnd_votes - pf_votes) as gap
        FROM polling_station_results
        GROUP BY constituency
        HAVING SUM(upnd_votes) > SUM(pf_votes)
        ORDER BY gap DESC
        LIMIT 5
    """)

    danger_zones = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "war_room.html",
        battleground=battleground,
        silent_stations=silent_stations,
        danger_zones=danger_zones
    )

# ==============================
# MAP DATA
# ==============================

@app.route("/map_data")
@login_required
def map_data():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT constituency,
               SUM(pf_votes),
               SUM(upnd_votes)
        FROM polling_station_results
        GROUP BY constituency
    """)

    data = {}

    for c, pf, upnd in cur.fetchall():
        if pf > upnd:
            status = "PF"
        elif upnd > pf:
            status = "UPND"
        else:
            status = "TIED"

        data[c] = {
            "pf": pf,
            "upnd": upnd,
            "status": status
        }

    cur.close()
    conn.close()

    return jsonify(data)

# ==============================
# ALERTS
# ==============================

@app.route("/alerts")
@login_required
def alerts():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT constituency,
               SUM(pf_votes) as pf,
               SUM(upnd_votes) as upnd
        FROM polling_station_results
        GROUP BY constituency
    """)

    alerts = []

    for c, pf, upnd in cur.fetchall():
        if upnd > pf:
            alerts.append({
                "constituency": c,
                "margin": upnd - pf
            })

    cur.close()
    conn.close()

    return jsonify(alerts)


# ==============================
# DASHBOARD
# ==============================

@app.route("/")
@login_required
@admin_required
def dashboard():

    conn = get_db()
    cur = conn.cursor()

    # ==============================
    # TOTAL MEMBERS
    # ==============================
    cur.execute("SELECT COUNT(*) FROM members WHERE status='Active'")
    total_members = cur.fetchone()[0]

    # ==============================
    # MEMBERS BY PROVINCE
    # ==============================
    cur.execute("""
        SELECT province, COUNT(*)
        FROM members
        WHERE status='Active'
        GROUP BY province
        ORDER BY COUNT(*) DESC
    """)
    provinces = cur.fetchall()

    # ==============================
    # NATIONAL BASELINE (CRITICAL)
    # ==============================
    cur.execute("""
        SELECT 
            COALESCE(SUM(total_voters),0),
            COALESCE(SUM(total_polling_stations),0)
        FROM constituency_stats
    """)
    total_voters, national_stations = cur.fetchone()

    # ==============================
    # REAL VOTES (LIVE DATA)
    # ==============================
    cur.execute("""
        SELECT 
            COALESCE(SUM(pf_votes),0),
            COALESCE(SUM(upnd_votes),0),
            COALESCE(SUM(other_votes),0)
        FROM polling_station_results
    """)
    pf_total, upnd_total, other_total = cur.fetchone()

    # ==============================
    # STATUS + MARGIN
    # ==============================
    margin = pf_total - upnd_total

    if pf_total > upnd_total:
        status = "WINNING"
    elif pf_total < upnd_total:
        status = "LOSING"
    else:
        status = "TIED"

    # ==============================
    # COVERAGE (FIELD CONTROL)
    # ==============================
    cur.execute("""
        SELECT COUNT(DISTINCT polling_station)
        FROM polling_station_results
    """)
    reporting_stations = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT polling_station)
        FROM agents
    """)
    total_stations = cur.fetchone()[0]

    coverage = 0
    if total_stations > 0:
        coverage = round((reporting_stations / total_stations) * 100, 1)

    # ==============================
    # EXPECTED TURNOUT MODEL
    # ==============================
    expected_votes = int(total_members * 0.65)

    # ==============================
    # TURNOUT GAP (CRITICAL SIGNAL)
    # ==============================
    vote_gap = expected_votes - pf_total

    # ==============================
    # WIN THRESHOLD (REAL POWER)
    # ==============================
    votes_needed_to_win = int((total_voters * 0.5) + 1)
    distance_to_majority = votes_needed_to_win - pf_total

    # ==============================
    # TURNOUT EFFICIENCY
    # ==============================
    turnout_efficiency = 0
    if expected_votes > 0:
        turnout_efficiency = round((pf_total / expected_votes) * 100, 1)

    # ==============================
    # RECENT RESULTS (LIVE FEED)
    # ==============================
    cur.execute("""
        SELECT polling_station, pf_votes, upnd_votes, other_votes
        FROM polling_station_results
        ORDER BY id DESC
        LIMIT 5
    """)
    recent_results = cur.fetchall()

    # ==============================
    # 🔥 TOP LOSING CONSTITUENCIES
    # ==============================
    cur.execute("""
        SELECT constituency,
               SUM(upnd_votes - pf_votes) AS gap
        FROM polling_station_results
        GROUP BY constituency
        HAVING SUM(upnd_votes) > SUM(pf_votes)
        ORDER BY gap DESC
        LIMIT 5
    """)
    danger_zones = cur.fetchall()

    # ==============================
    # 🔥 STRONGHOLDS
    # ==============================
    cur.execute("""
        SELECT constituency,
               SUM(pf_votes - upnd_votes) AS lead
        FROM polling_station_results
        GROUP BY constituency
        HAVING SUM(pf_votes) > SUM(upnd_votes)
        ORDER BY lead DESC
        LIMIT 5
    """)
    strongholds = cur.fetchall()

    cur.close()
    conn.close()

    # ==============================
    # SYSTEM STATUS
    # ==============================
    system_status = {
        "telegram": "OK",
        "database": "Connected",
        "server": "Running"
    }

    return render_template(
        "index.html",

        # BASIC
        total_members=total_members,
        provinces=provinces,

        # VOTES
        pf_total=pf_total,
        upnd_total=upnd_total,
        other_total=other_total,
        margin=margin,
        status=status,

        # FIELD CONTROL
        coverage=coverage,
        reporting_stations=reporting_stations,
        total_stations=total_stations,

        # NATIONAL POWER METRICS
        total_voters=total_voters,
        national_stations=national_stations,
        expected_votes=expected_votes,
        vote_gap=vote_gap,
        votes_needed_to_win=votes_needed_to_win,
        distance_to_majority=distance_to_majority,
        turnout_efficiency=turnout_efficiency,

        # INTELLIGENCE
        recent_results=recent_results,
        danger_zones=danger_zones,
        strongholds=strongholds,

        # SYSTEM
        system_status=system_status
    )

# ==============================
# POLLING INTELLIGENCE
# ==============================

@app.route("/polling_intelligence")
@login_required
def polling_intelligence():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            cs.constituency,
            cs.province,

            COUNT(DISTINCT m.membership_id) AS members,
            cs.total_voters,
            cs.total_polling_stations,

            COALESCE(SUM(r.pf_votes), 0) AS pf_votes,
            COALESCE(SUM(r.upnd_votes), 0) AS upnd_votes,

            COUNT(DISTINCT r.polling_station) AS reporting_stations

        FROM constituency_stats cs

        LEFT JOIN members m
            ON m.constituency = cs.constituency
            AND m.status = 'Active'

        LEFT JOIN polling_station_results r
            ON r.constituency = cs.constituency

        GROUP BY 
            cs.constituency,
            cs.province,
            cs.total_voters,
            cs.total_polling_stations

        ORDER BY 
            cs.province ASC,
            cs.constituency ASC
    """)

    rows = cur.fetchall()

    stations = []

    for r in rows:
        (
            constituency,
            province,
            members,
            voters,
            total_stations,
            pf_votes,
            upnd_votes,
            reporting_stations
        ) = r

        # =========================
        # CORE METRICS
        # =========================

        penetration = round((members / voters) * 100, 2) if voters else 0
        margin = pf_votes - upnd_votes
        turnout = pf_votes + upnd_votes

        coverage = round(
            (reporting_stations / total_stations) * 100,
            2
        ) if total_stations else 0

        # =========================
        # STRATEGIC CLASSIFICATION
        # =========================

        if margin > 0 and penetration >= 40:
            status = "STRONG"
        elif margin < 0 and penetration < 30:
            status = "WEAK"
        else:
            status = "BATTLEGROUND"

        # =========================
        # ACTION ENGINE
        # =========================

        if coverage < 50:
            action = "DEPLOY REPORTING TEAMS"
        elif margin < 0:
            action = "RECOVER SUPPORT"
        else:
            action = "MAINTAIN CONTROL"

        # =========================
        # FINAL STRUCTURE
        # =========================

        stations.append({
            "constituency": constituency,
            "province": province,
            "members": members,
            "voters": voters,
            "total_stations": total_stations,
            "reporting_stations": reporting_stations,
            "coverage": coverage,

            "pf_votes": pf_votes,
            "upnd_votes": upnd_votes,
            "margin": margin,
            "turnout": turnout,

            "penetration": penetration,
            "status": status,
            "action": action
        })

    cur.close()
    conn.close()

    return render_template(
        "polling_intelligence.html",
        stations=stations
    )

# ==============================
# ANALYTICS ROUTE
# ==============================

@app.route("/analytics")
@login_required
def analytics():

    conn = get_db()
    cur = conn.cursor()

    # ==============================
    # MEMBERS BY PROVINCE
    # ==============================
    cur.execute("""
        SELECT province, COUNT(*)
        FROM members
        WHERE status='Active'
        GROUP BY province
        ORDER BY COUNT(*) DESC
    """)
    provinces = cur.fetchall()

    # ==============================
    # NATIONAL BASELINE
    # ==============================
    cur.execute("""
        SELECT province, SUM(total_voters)
        FROM constituency_stats
        GROUP BY province
    """)
    voters_data = dict(cur.fetchall())

    # ==============================
    # REAL VOTES BY PROVINCE
    # ==============================
    cur.execute("""
        SELECT province,
               COALESCE(SUM(pf_votes),0),
               COALESCE(SUM(upnd_votes),0)
        FROM polling_station_results
        GROUP BY province
    """)
    votes_data = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    # ==============================
    # BUILD INTELLIGENCE
    # ==============================
    analytics = []

    for province, members in provinces:

        voters = voters_data.get(province, 0)
        pf_votes, upnd_votes = votes_data.get(province, (0, 0))

        penetration = round((members / voters) * 100, 2) if voters > 0 else 0
        expected_votes = int(members * 0.65)
        margin = pf_votes - upnd_votes

        # ==============================
        # STATUS CLASSIFICATION
        # ==============================
        if margin > 0 and penetration >= 40:
            status = "STRONGHOLD"
        elif margin < 0 and penetration < 30:
            status = "WEAK"
        else:
            status = "BATTLEGROUND"

        analytics.append({
            "province": province,
            "members": members,
            "voters": voters,
            "pf_votes": pf_votes,
            "upnd_votes": upnd_votes,
            "penetration": penetration,
            "expected_votes": expected_votes,
            "margin": margin,
            "status": status
        })

    cur.close()
    conn.close()

    return render_template(
        "analytics.html",
        analytics=analytics
    )

# ==============================
# AGENTS LIST
# ==============================

@app.route("/agents", methods=["GET", "POST"])
@login_required
@admin_required
def agents():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        province = request.form.get("province")
        constituency = request.form.get("constituency")
        polling_station = request.form.get("polling_station")

        cur.execute("""
            INSERT INTO agents (name, phone, province, constituency, polling_station)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, phone, province, constituency, polling_station))

        conn.commit()

    cur.execute("""
        SELECT agent_id, name, phone, province, constituency, polling_station, active
        FROM agents
        ORDER BY agent_id DESC
    """)

    agents = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("agents.html", agents=agents)

# ==============================
# TOGGLE AGENT
# ==============================

@app.route("/toggle_agent/<int:agent_id>")
@login_required
def toggle_agent(agent_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE agents
        SET active = NOT active
        WHERE agent_id = %s
    """, (agent_id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/agents")

# ==============================
# MEMBERS LIST
# ==============================

@app.route("/members")
@login_required
@admin_required
def members():
    key = request.args.get("key")

    if key != os.getenv("ADMIN_KEY"):
        return {"error": "Unauthorized"}, 403

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT membership_id,full_name,province,district,constituency,phone,status
    FROM members
    ORDER BY full_name
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    members = []

    for r in rows:

        members.append({
            "membership_id": r[0],
            "full_name": r[1],
            "province": r[2],
            "district": r[3],
            "constituency": r[4],
            "phone": r[5],
            "status": r[6]
        })


    return render_template("members.html", members=members)

# ==============================
# EDIT MEMBER
# ==============================

@app.route("/edit/<membership_id>", methods=["GET","POST"])
@login_required
def edit_member(membership_id):

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        cur.execute("""
        UPDATE members
        SET full_name=%s,
            province=%s,
            district=%s,
            constituency=%s,
            phone=%s,
            status=%s
        WHERE membership_id=%s
        """,(
            request.form["full_name"],
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

    cur.execute(
        "SELECT * FROM members WHERE membership_id=%s",
        (membership_id,)
    )

    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return "Member not found"

    columns = [desc[0] for desc in cur.description]
    member = dict(zip(columns, row))

    cur.close()
    conn.close()

    return render_template("edit_member.html", member=member)

# ==============================
# SEARCH MEMBERS
# ==============================

@app.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()

    if not q:
        return jsonify([])

    conn = None

    try:
        conn = get_db()
        cur = conn.cursor()

        query = """
            SELECT membership_id, full_name, phone, province, district, constituency, status
            FROM members
            WHERE LOWER(full_name) LIKE %s
               OR LOWER(phone) LIKE %s
            ORDER BY full_name
            LIMIT 50
        """

        param = f"%{q.lower()}%"
        cur.execute(query, (param, param))

        rows = cur.fetchall()

        results = []
        for r in rows:
            results.append({
                "membership_id": r[0],
                "full_name": r[1],
                "phone": r[2],
                "province": r[3],
                "district": r[4],
                "constituency": r[5],
                "status": r[6]
            })

        cur.close()
        return jsonify(results)

    except Exception as e:
        print("SEARCH ERROR:", e)
        return jsonify({"error": "Search failed"}), 500

    finally:
        if conn:
            conn.close()

# ==============================
# SEND CARD TO EXISTING MEMBER
# ==============================

def send_cards_to_existing_members():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT membership_id, full_name, province, constituency, chat_id
        FROM members
        WHERE status = 'Active'
    """)

    members = cur.fetchall()

    sent = 0

    for m in members:
        member_id, name, province, constituency, chat_id = m

        # Skip users without Telegram chat_id
        if not chat_id:
            continue

        try:
            # Generate QR
            qr_path = generate_qr(member_id)

            # Generate card
            card_path = generate_membership_card(
                name, province, constituency, member_id
            )

            # Send
            send_telegram_message(chat_id, f"Your Membership ID: {member_id}")
            send_photo(chat_id, qr_path)
            send_photo(chat_id, card_path)

            sent += 1

        except Exception as e:
            print(f"Error sending to {member_id}: {e}")

    cur.close()
    conn.close()

    return sent

@app.route("/send_existing_cards")
@login_required
def send_existing_cards():
    key = request.args.get("key")

    if key != os.getenv("ADMIN_KEY", "pfp_secure_12345"):
        return {"error": "Unauthorized"}, 403

    count = send_cards_to_existing_members()

    return {"message": f"Cards sent to {count} members"}

# ==============================
# DELETE MEMBER
# ==============================

@app.route("/delete_member/<membership_id>")
@login_required
def delete_member(membership_id):

    key = request.args.get("key")
    if key != os.getenv("EXPORT_KEY"):
        return {"error": "Unauthorized"}, 403

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM members WHERE membership_id=%s",
        (membership_id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    return {"message": "Member deleted"}

# ==============================
# EXPORT MEMBER
# ==============================

import os
import psycopg2
from flask import send_file, request
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from tempfile import NamedTemporaryFile

load_dotenv()


@app.route("/export_excel")
@login_required
def export_excel():

    if request.args.get("key") != os.getenv("EXPORT_KEY"):
        return {"error": "Unauthorized"}, 403

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT membership_id, full_name, phone, province, district, constituency, status
        FROM members
        ORDER BY full_name
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Members"

    headers = ["Membership ID", "Full Name", "Phone", "Province", "District", "Constituency", "Status"]
    ws.append(headers)

    for row in rows:
        ws.append(row)

    temp_file = NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp_file.name)

    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name="members.xlsx"
    )
