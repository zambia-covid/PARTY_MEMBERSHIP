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
from auth import role_required
from flask import session

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

# ==============================
# 🗺️ CONSTITUENCY → DISTRICT MAP
# ==============================
CONSTITUENCY_TO_DISTRICT = {

    # LUSAKA
    "kabwata": "lusaka",
    "kamwala": "lusaka",
    "lusaka central": "lusaka",
    "matero": "lusaka",
    "munali": "lusaka",
    "chawama": "lusaka",
    "kanyama": "lusaka",
    "mandevu": "lusaka",
    "rufunsa": "rufunsa",
    "chilanga": "chilanga",
    "chongwe": "chongwe",
    "kafue": "kafue",

    # COPPERBELT
    "ndola central": "ndola",
    "kabushi": "ndola",
    "chifubu": "ndola",
    "kitwe central": "kitwe",
    "nkana": "kitwe",
    "chimwemwe": "kitwe",
    "kwacha": "kitwe",

    # EASTERN
    "chipata central": "chipata",
    "chadiza": "chadiza",
    "katete": "katete",
    "petauke central": "petauke",
    "lundazi": "lundazi",

    # SOUTHERN
    "livingstone": "livingstone",
    "mazabuka central": "mazabuka",
    "monze central": "monze",
    "choma central": "choma",
    "kalomo central": "kalomo",

    # CENTRAL
    "kabwe central": "kabwe",
    "bwacha": "kabwe",
    "kapiri mposhi": "kapiri mposhi",
    "mkushi": "mkushi",

    # NORTHERN
    "kasama central": "kasama",
    "mpika": "mpika",
    "mbala": "mbala",

    # LUAPULA
    "mansa central": "mansa",
    "bahati": "mansa",
    "samfya": "samfya",

    # NORTH-WESTERN
    "solwezi central": "solwezi",
    "kalumbila": "kalumbila",

    # WESTERN
    "mongu central": "mongu",
    "senanga": "senanga"
}

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
# BUILD POLLING INTELLIGENCE
# ======================
def build_polling_intelligence(cur):

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
        penetration = (members / voters * 100) if voters else 0
        margin = pf_votes - upnd_votes
        turnout = pf_votes + upnd_votes
        coverage = (reporting_stations / total_stations * 100) if total_stations else 0

        # =========================
        # BASELINE INTELLIGENCE
        # =========================

        # voter importance
        if voters >= 80000:
            voter_weight = "HIGH VALUE"
        elif voters >= 40000:
            voter_weight = "MEDIUM VALUE"
        else:
            voter_weight = "LOW VALUE"

        # visibility
        if coverage < 40:
            visibility = "BLIND"
        elif coverage < 70:
            visibility = "PARTIAL"
        else:
            visibility = "FULL"

        # =========================
        # ADVANCED INTELLIGENCE
        # =========================

        # win classification
        if margin > 0 and coverage >= 70:
            win_type = "REAL WIN"
        elif margin > 0:
            win_type = "FAKE WIN"
        else:
            win_type = "NOT WINNING"

        # structure strength
        if penetration >= 40:
            structure = "STRONG BASE"
        elif penetration < 25:
            structure = "WEAK BASE"
        else:
            structure = "AVERAGE BASE"

        # risk detection
        if coverage < 40 and voters > 50000:
            risk = "CRITICAL BLIND SPOT"
        elif margin < 0 and penetration < 30:
            risk = "LOSING GROUND"
        elif margin > 0 and coverage < 50:
            risk = "UNSTABLE LEAD"
        else:
            risk = "STABLE"

        # =========================
        # FINAL STATUS
        # =========================

        if margin > 0 and penetration >= 40 and coverage >= 70:
            status = "SECURE"
        elif margin < 0 and penetration < 30:
            status = "COLLAPSE"
        else:
            status = "BATTLEGROUND"

        # =========================
        # ACTION ENGINE
        # =========================

        if coverage < 50:
            action = "DEPLOY REPORTING TEAMS"
        elif margin < 0 and penetration < 30:
            action = "REBUILD STRUCTURE"
        elif margin < 0:
            action = "RECOVER VOTES"
        elif coverage < 70:
            action = "VERIFY LEAD"
        else:
            action = "MAINTAIN CONTROL"

        # =========================
        # CRITICAL FLAGS
        # =========================

        fake_win = (margin > 0 and coverage < 70)
        blind_zone = (coverage < 40 and voters > 50000)
        weak_structure = (penetration < 25 and voters > 50000)

        # =========================
        # PRIORITY SCORE
        # =========================

        priority = 0

        if status == "COLLAPSE":
            priority += 3
        if blind_zone:
            priority += 3
        if fake_win:
            priority += 2
        if coverage < 50:
            priority += 2

        # =========================
        # FINAL OBJECT
        # =========================

        stations.append({
            "constituency": constituency,
            "province": province,

            "members": members,
            "voters": voters,
            "total_stations": total_stations,
            "reporting_stations": reporting_stations,

            "coverage": round(coverage, 2),
            "penetration": round(penetration, 2),

            "pf_votes": pf_votes,
            "upnd_votes": upnd_votes,
            "margin": margin,
            "turnout": turnout,

            "status": status,
            "win_type": win_type,
            "structure": structure,
            "risk": risk,
            "action": action,

            "voter_weight": voter_weight,
            "visibility": visibility,

            "fake_win": fake_win,
            "blind_zone": blind_zone,
            "weak_structure": weak_structure,

            "priority": priority
        })

    # 🔥 MOST IMPORTANT FIRST
    stations.sort(key=lambda x: x["priority"], reverse=True)

    return stations

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

def hash_password(password):
    return generate_password_hash(password)

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
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role

# ======================
# USER LOADER 
# ======================
@login_manager.user_loader
def load_user(user_id):

    if user_id == "admin":
        return User("admin", "admin")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT username, role, province, district
        FROM users
        WHERE username=%s
    """, (user_id,))

    user = cur.fetchone()

    cur.close()
    conn.close()

    if user:
        u = User(user[0], user[1])
        u.province = user[2]
        u.district = user[3]
        return u

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

@app.route("/api/district_summary")
@login_required
def district_summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            district,
            COUNT(*) as total,

            SUM(CASE WHEN severity='Critical' THEN 1 ELSE 0 END),
            SUM(CASE WHEN severity='High' THEN 1 ELSE 0 END),
            SUM(CASE WHEN severity='Medium' THEN 1 ELSE 0 END),
            SUM(CASE WHEN severity='Low' THEN 1 ELSE 0 END),

            SUM(
                CASE 
                    WHEN severity='Critical' THEN 3
                    WHEN severity='High' THEN 2
                    ELSE 1
                END
            ) as score

        FROM incidents
        GROUP BY district
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        (r[0] or "").lower().strip(): {
            "total": r[1],
            "critical": r[2],
            "high": r[3],
            "medium": r[4],
            "low": r[5],
            "score": int(r[6] or 0)
        }
        for r in rows
    })

@app.route("/download_card/<member_id>")
def download_card(member_id):
    path = f"cards/{member_id}.png"

    if not os.path.exists(path):
        return "Card not found", 404

    return send_file(path, as_attachment=True)

# ==============================
# API PROVINCES
# ==============================
@app.route("/api/provinces")
def provinces_api():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT province, total_voters
        FROM provinces
        ORDER BY total_voters DESC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify([
        {"province": r[0], "voters": r[1]}
        for r in rows
    ])

from flask import jsonify

@app.route("/api/provinces_list")
def provinces_list():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT province
        FROM constituencies
        ORDER BY province
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify([r[0] for r in rows])

@app.route("/api/constituencies")
def constituencies():

    province = request.args.get("province")

    cur = get_db().cursor()

    cur.execute("""
        SELECT constituency
        FROM constituencies
        WHERE province=%s
        ORDER BY constituency
    """, (province,))

    data = [r[0] for r in cur.fetchall()]
    return jsonify(data)

# ==============================
# CREATE USER
# ==============================
from flask import request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user

@app.route("/create_user", methods=["GET", "POST"])
@login_required
def create_user():

    # 🔒 Restrict access
    if current_user.role not in ["admin", "national_manager", "provincial_manager"]:
        flash("Unauthorized access")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]
        province = request.form.get("province")
        district = request.form.get("district")

        # 🔒 Role enforcement
        if current_user.role == "provincial_manager":
            province = current_user.province

            if role == "national_manager":
                flash("You cannot create a national manager")
                return redirect(url_for("create_user"))

        # 🔒 Validation
        if not username or not password or not role:
            flash("Missing required fields")
            return redirect(url_for("create_user"))

        # 🔐 Hash password
        hashed_password = hash_password(password)

        try:
            query_db("""
                INSERT INTO users (username, password, role, province, district)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, hashed_password, role, province, district))

            flash("User created successfully")

        except Exception as e:
            print(e)
            flash("Error creating user (possibly duplicate username)")

        return redirect(url_for("create_user"))

    return render_template("create_user.html")
    
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

from werkzeug.security import check_password_hash
from flask import request, redirect, render_template, url_for, flash
from flask_login import login_user, current_user

from werkzeug.security import check_password_hash
from flask import request, redirect, render_template, url_for, flash
from flask_login import login_user, current_user

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        print("\n========== LOGIN ATTEMPT ==========")
        print("USERNAME ENTERED:", username)
        print("PASSWORD ENTERED:", password)

        if not username or not password:
            flash("Enter username and password", "danger")
            print("❌ Missing username or password")
            return redirect(url_for("login"))

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT username, password, role
                FROM users
                WHERE username=%s
            """, (username,))

            user = cur.fetchone()

            print("DB RESULT:", user)

        except Exception as e:
            print("🔥 LOGIN QUERY ERROR:", e)
            flash("System error during login", "danger")
            return redirect(url_for("login"))

        finally:
            cur.close()
            conn.close()

        # =========================
        # 🔍 DEBUG BLOCK
        # =========================
        if user:
            print("✅ USER FOUND")
            print("HASH IN DB:", user[1])

            try:
                match = check_password_hash(user[1], password)
                print("PASSWORD MATCH:", match)
            except Exception as e:
                print("🔥 HASH CHECK ERROR:", e)
                match = False
        else:
            print("❌ NO USER FOUND")
            match = False

        # =========================
        # 🔐 LOGIN LOGIC
        # =========================
        if user and match:

            print("🎯 LOGIN SUCCESS")

            user_obj = User(id=user[0], role=user[2])
            login_user(user_obj)

            # Role-based redirect
            if user[2] == "national_manager":
                return redirect(url_for("dashboard"))

            elif user[2] == "provincial_manager":
                return redirect("/provincial_dashboard")

            elif user[2] == "agent":
                return redirect("/agent_dashboard")

            else:
                return redirect("/")

        print("❌ LOGIN FAILED")
        flash("Invalid username or password", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect("/login")
    
@app.route("/api/live_dashboard")
@login_required
def live_dashboard():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT constituency,
               COALESCE(SUM(pf_votes),0),
               COALESCE(SUM(upnd_votes),0)
        FROM polling_station_results
        GROUP BY constituency
    """)

    data = []

    for c, pf, upnd in cur.fetchall():
        margin = pf - upnd

        if margin > 0:
            status = "WIN"
        elif margin < 0:
            status = "LOSE"
        else:
            status = "TOSS-UP"

        data.append({
            "constituency": c,
            "pf": pf,
            "upnd": upnd,
            "margin": margin,
            "status": status
        })

    cur.close()
    conn.close()

    return jsonify(data)

@app.route("/api/map_intelligence")
@login_required
def map_intelligence():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT constituency,
               SUM(pf_votes),
               SUM(upnd_votes)
        FROM polling_station_results
        GROUP BY constituency
    """)

    map_data = []
    alerts = []

    for c, pf, upnd in cur.fetchall():

        margin = (pf or 0) - (upnd or 0)

        if margin > 1000:
            heat = "strong_pf"
        elif margin > 0:
            heat = "lean_pf"
        elif margin < -1000:
            heat = "strong_upnd"
        elif margin < 0:
            heat = "lean_upnd"
        else:
            heat = "neutral"

        map_data.append({
            "constituency": c,
            "pf": pf,
            "upnd": upnd,
            "margin": margin,
            "heat": heat
        })

        # 🔥 Alert zones
        if abs(margin) < 500:
            alerts.append({"constituency": c})

    cur.close()
    conn.close()

    return jsonify({
        "map": map_data,
        "alerts": alerts
    })

@app.route("/api/turnout_targets")
@login_required
def turnout_targets():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            polling_station,
            COUNT(m.membership_id) as members,
            COALESCE(SUM(r.pf_votes + r.upnd_votes),0) as votes
        FROM members m
        LEFT JOIN polling_station_results r
        ON m.polling_station = r.polling_station
        GROUP BY polling_station
    """)

    targets = []

    for station, members, votes in cur.fetchall():

        gap = members - votes

        if gap > 200:
            priority = "HIGH"
        elif gap > 100:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        targets.append({
            "station": station,
            "gap": gap,
            "priority": priority
        })

    cur.close()
    conn.close()

    return jsonify(targets)

@app.route("/api/strategy")
@login_required
def strategy():

    conn = get_db()
    cur = conn.cursor()

    # ==============================
    # 🔴 NATIONAL TOTALS
    # ==============================
    cur.execute("""
        SELECT 
            COALESCE(SUM(pf_votes),0),
            COALESCE(SUM(upnd_votes),0)
        FROM polling_station_results
    """)

    pf, upnd = cur.fetchone()
    margin = pf - upnd

    # ==============================
    # 📍 PROVINCIAL BREAKDOWN
    # ==============================
    cur.execute("""
        SELECT 
            p.province,
            p.total_voters,
            COALESCE(SUM(r.pf_votes),0) AS pf_votes,
            COALESCE(SUM(r.upnd_votes),0) AS upnd_votes
        FROM provinces p
        LEFT JOIN polling_station_results r
            ON p.province = r.province
        GROUP BY p.province, p.total_voters
        ORDER BY p.total_voters DESC
    """)

    rows = cur.fetchall()

    province_lines = []

    for r in rows:
        province = r[0]
        voters = r[1]
        pf_votes = r[2]
        upnd_votes = r[3]

        turnout = (pf_votes + upnd_votes)
        turnout_pct = (turnout / voters * 100) if voters else 0

        province_lines.append(
            f"{province}: {voters} voters | PF {pf_votes} vs UPND {upnd_votes} | turnout {turnout_pct:.1f}%"
        )

    province_breakdown = "\n".join(province_lines)

    # ==============================
    # 🧠 STRATEGY PROMPT
    # ==============================
    prompt = f"""
National election situation:

{province_breakdown}

Total PF: {pf}
Total UPND: {upnd}
Margin: {margin}

Give a sharp strategic directive (max 25 words).
Focus on:
- high voter provinces
- weak performance areas
- immediate action
"""

    # ==============================
    # 🤖 AI CALL
    # ==============================
    try:
        res = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        advice = res.output_text.strip()

    except Exception as e:
        print("Strategy error:", e)

        # 🔴 fallback (never leave blank)
        if margin < 0:
            advice = "Recover urban turnout, reinforce Copperbelt, protect strongholds, deploy rapid mobilization in high voter provinces."
        else:
            advice = "Defend strongholds, increase turnout in key provinces, monitor weak margins, sustain mobilization pressure."

    # ==============================
    # 🔒 CLEANUP
    # ==============================
    cur.close()
    conn.close()

    return jsonify({
        "advice": advice,
        "margin": margin,
        "pf": pf,
        "upnd": upnd
    })

# ==============================
# CONSTITUENCY INTELLIGENCE
# ==============================
@app.route("/constituency_intelligence")
@login_required
def constituency_intelligence():
    return render_template("constituency_intelligence.html")

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
#  SUBMIT RESULTS
# ==============================
@app.route('/submit_results', methods=['GET', 'POST'])
@login_required
@agent_required
def submit_results():

    if request.method == 'POST':

        try:
            pf = int(request.form.get("pf", 0))
            upnd = int(request.form.get("upnd", 0))
            other = int(request.form.get("other", 0))
        except:
            return "Invalid input", 400

        # 🔴 BASIC VALIDATION
        if pf < 0 or upnd < 0 or other < 0:
            return "Votes cannot be negative", 400

        total_votes = pf + upnd + other

        if total_votes == 0:
            return "Total votes cannot be zero", 400

        agent_id = current_user.id

        conn = get_db()
        cur = conn.cursor()

        # ==============================
        # 🔴 GET AGENT DETAILS
        # ==============================
        cur.execute("""
            SELECT province, constituency, polling_station
            FROM agents
            WHERE agent_id=%s
        """, (agent_id,))
        agent = cur.fetchone()

        if not agent:
            return "Agent not found", 404

        province, constituency, polling_station = agent

        # ==============================
        # 🔴 CHECK DUPLICATE SUBMISSION
        # ==============================
        cur.execute("""
            SELECT 1 FROM polling_station_results
            WHERE polling_station=%s
            LIMIT 1
        """, (polling_station,))

        if cur.fetchone():
            return "Results already submitted for this station", 400

        # ==============================
        # 🔴 OPTIONAL: VOTER LIMIT CHECK
        # ==============================
        cur.execute("""
            SELECT total_voters
            FROM constituencies
            WHERE constituency=%s
        """, (constituency,))

        row = cur.fetchone()

        if row:
            max_voters = row[0]
            if total_votes > max_voters:
                return "Votes exceed registered voters", 400

        # ==============================
        # 🔴 INSERT RESULTS
        # ==============================
        cur.execute("""
            INSERT INTO polling_station_results
            (agent_id, province, constituency, polling_station, pf_votes, upnd_votes, other_votes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            agent_id,
            province,
            constituency,
            polling_station,
            pf,
            upnd,
            other
        ))

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
    
# ==============================
# INCIDENTS
# ==============================
@app.route("/incidents")
@login_required
def incidents_page():
    return render_template("incidents.html")

import os
from flask import request, render_template, redirect, session
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "static/uploads"

# ensure folder exists (important on Render)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/incident_map")
@login_required
def incident_map():
    return render_template("incident_map.html")

@app.route("/report_incident", methods=["GET", "POST"])
@login_required
def report_incident():

    if request.method == "POST":

        conn = get_db()
        cur = conn.cursor()

        try:
            # =========================
            # 🧾 INPUTS
            # =========================
            constituency = request.form.get("constituency", "").strip()
            province = request.form.get("province")
            incident_type = request.form.get("type")
            severity = request.form.get("severity")
            description = request.form.get("description")
            contact = request.form.get("contact")

            # 🔴 NORMALIZE KEY
            key = constituency.lower()

            # 🔴 MAP TO DISTRICT
            district = CONSTITUENCY_TO_DISTRICT.get(key, key)

            # =========================
            # 📸 HANDLE PHOTO
            # =========================
            photo = request.files.get("photo")
            filename = None

            if photo and photo.filename != "":
                filename = secure_filename(photo.filename)

                filepath = os.path.join(UPLOAD_FOLDER, filename)

                counter = 1
                while os.path.exists(filepath):
                    name, ext = os.path.splitext(filename)
                    filename = f"{name}_{counter}{ext}"
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    counter += 1

                photo.save(filepath)

            # =========================
            # 📍 GPS
            # =========================
            latitude = request.form.get("latitude")
            longitude = request.form.get("longitude")

            # Convert safely
            try:
                latitude = float(latitude) if latitude else None
                longitude = float(longitude) if longitude else None
            except:
                latitude = None
                longitude = None

            # =========================
            # 🧾 INSERT
            # =========================
            cur.execute("""
                INSERT INTO incidents (
                    type,
                    province,
                    constituency,
                    district,
                    severity,
                    description,
                    contact,
                    photo,
                    latitude,
                    longitude,
                    status,
                    created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Open', NOW())
            """, (
                incident_type,
                province,
                constituency,
                district,   # 🔥 NEW (alignment fix)
                severity,
                description,
                contact,
                filename,
                latitude,
                longitude
            ))

            conn.commit()

        except Exception as e:
            conn.rollback()
            print("REPORT INCIDENT ERROR:", e)
            return "Error saving incident", 500

        finally:
            cur.close()
            conn.close()

        return redirect("/agent_dashboard")

    return render_template("report_incident.html")

@app.route("/api/my_incidents")
@login_required
def my_incidents():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            id,
            type,
            province,
            constituency,
            district,
            severity,
            description,
            status,
            created_at,
            latitude,
            longitude
        FROM incidents
        WHERE COALESCE(status,'Open') != 'Deleted'
        ORDER BY created_at DESC
        LIMIT 50
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "type": r[1],
            "province": r[2],
            "constituency": r[3],
            "district": (r[4] or "").lower().strip(),  # 🔥 REQUIRED
            "severity": r[5],
            "description": r[6],
            "status": r[7],
            "created_at": str(r[8]),
            "lat": float(r[9]) if r[9] else None,      # 🔥 MAP READY
            "lng": float(r[10]) if r[10] else None
        }
        for r in rows
    ])

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
            type,
            province,
            constituency,
            district,
            severity,
            description,
            status,
            created_at,
            latitude,
            longitude
        FROM incidents
        WHERE COALESCE(status,'Open') != 'Deleted'
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "type": r[1],
            "province": r[2],
            "constituency": r[3],
            "district": (r[4] or "").lower().strip(),  # 🔥 KEY FIX
            "severity": r[5],
            "description": r[6],
            "status": r[7],
            "created_at": str(r[8]),
            "lat": float(r[9]) if r[9] else None,
            "lng": float(r[10]) if r[10] else None
        }
        for r in rows
    ])

# ==============================
# RESOLVE ACCIDENTS
# ==============================
@app.route("/resolve/<incident_id>", methods=["POST"])
@login_required
def resolve_incident(incident_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE incidents
        SET status = 'Resolved'
        WHERE id = %s
    """, (incident_id,))

    conn.commit()
    cur.close()
    conn.close()

    return {"status": "ok"}
    
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
# AGENT LOGIN
# ==============================
@app.route("/agent_login", methods=["GET", "POST"])
def agent_login():

    if current_user.is_authenticated:
        return redirect(url_for("agent_dashboard"))

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()

        if not phone or not password:
            return render_template("agent_login.html", error="Enter phone and password")

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT agent_id, password, role, province, constituency, polling_station
            FROM agents
            WHERE phone=%s
        """, (phone,))

        user = cur.fetchone()

        cur.close()
        conn.close()

        if user and check_password_hash(user[1], password):

            user_obj = User(
                id=user[0],
                role=user[2]
            )

            # 🔥 attach extra context
            user_obj.province = user[3]
            user_obj.constituency = user[4]
            user_obj.polling_station = user[5]

            login_user(user_obj)

            next_page = request.args.get("next")
            return redirect(next_page or url_for("agent_dashboard"))

        return render_template("agent_login.html", error="Invalid login")

    return render_template("agent_login.html")

# ==============================
# AGENT DASHBOARD
# ==============================
@app.route("/agent_dashboard")
@login_required
def agent_dashboard():

    if current_user.role not in ["agent", "admin"]:
        return "Forbidden", 403

    return render_template("agent_dashboard.html")

# ==============================
# WAR ROOM
# ==============================
@app.route("/war_room")
@login_required
@admin_required
def war_room():

    conn = get_db()
    cur = conn.cursor()

    # =========================
    # CORE INTELLIGENCE
    # =========================
    stations = build_polling_intelligence(cur)

    secure, collapse, battleground = [], [], []
    fake_wins, blind_spots, weak_structures, high_value_targets = [], [], [], []

    for s in stations:

        if s["status"] == "SECURE":
            secure.append(s)
        elif s["status"] == "COLLAPSE":
            collapse.append(s)
        else:
            battleground.append(s)

        if s.get("fake_win"):
            fake_wins.append(s)

        if s.get("blind_zone"):
            blind_spots.append(s)

        if s.get("weak_structure"):
            weak_structures.append(s)

        if s.get("voter_weight") == "HIGH VALUE":
            high_value_targets.append(s)

    # =========================
    # PRIORITY SORTING
    # =========================
    fake_wins = sorted(fake_wins, key=lambda x: x["priority"], reverse=True)[:5]
    blind_spots = sorted(blind_spots, key=lambda x: x["priority"], reverse=True)[:5]
    weak_structures = sorted(weak_structures, key=lambda x: x["priority"], reverse=True)[:5]

    high_value_targets = sorted(
        high_value_targets,
        key=lambda x: x["voters"],
        reverse=True
    )[:5]

    danger_zones = sorted(
        collapse,
        key=lambda x: x["margin"]
    )[:5]

    # =========================
    # SILENT STATIONS
    # =========================
    cur.execute("""
        SELECT a.polling_station
        FROM agents a
        LEFT JOIN polling_station_results r
            ON a.polling_station = r.polling_station
        WHERE r.id IS NULL
    """)

    silent_stations = [r[0] for r in cur.fetchall()]

    # =========================
    # MAP DATA (SOURCE OF TRUTH)
    # =========================
    cur.execute("""
        SELECT constituency,
               COALESCE(SUM(pf_votes),0) as pf,
               COALESCE(SUM(upnd_votes),0) as upnd
        FROM polling_station_results
        WHERE constituency IS NOT NULL
        GROUP BY constituency
    """)

    map_data = []

    for c, pf, upnd in cur.fetchall():

        constituency = (c or "").strip()
        margin = pf - upnd

        if margin > 0:
            status = "WIN"
        elif margin < 0:
            status = "LOSE"
        else:
            status = "TOSS-UP"

        map_data.append({
            "constituency": constituency,
            "pf": int(pf),
            "upnd": int(upnd),
            "margin": int(margin),
            "status": status
        })

    # =========================
    # SUMMARY (🔥 FIXED)
    # =========================
    summary = {
        "win": sum(1 for r in map_data if r["status"] == "WIN"),
        "lose": sum(1 for r in map_data if r["status"] == "LOSE"),
        "toss": sum(1 for r in map_data if r["status"] == "TOSS-UP")
    }

    cur.close()
    conn.close()

    return render_template(
        "war_room.html",
        stations=stations,
        summary=summary,
        danger_zones=danger_zones,
        fake_wins=fake_wins,
        blind_spots=blind_spots,
        weak_structures=weak_structures,
        high_value_targets=high_value_targets,
        silent_stations=silent_stations,
        map_data=map_data
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

    stations = build_polling_intelligence(cur)

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
        WHERE COALESCE(is_deleted, FALSE) = FALSE
        ORDER BY full_name
        LIMIT %s OFFSET %s
    """, (per_page, offset))

    rows = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM members WHERE COALESCE(is_deleted, FALSE) = FALSE")
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

# ==============================
# EDIT MEMBER
# ==============================
@app.route("/edit/<membership_id>", methods=["GET","POST"])
@login_required
@admin_required
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
@app.route("/delete/<membership_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_member(membership_id):

    conn = get_db()
    cur = conn.cursor()

    # ✅ SOFT DELETE (DON’T LOSE DATA)
    cur.execute("""
        UPDATE members
        SET is_deleted = TRUE
        WHERE membership_id = %s
    """, (membership_id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/members")

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
