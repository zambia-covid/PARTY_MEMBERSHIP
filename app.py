import os
import random
import qrcode
import psycopg2
import requests

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, redirect, Response, session
from twilio.rest import Client
from PIL import Image, ImageDraw, ImageFont
from datetime import date

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# ==============================
# ENVIRONMENT
# ==============================

ENV = os.getenv("ENV", "development")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Missing BOT_TOKEN")

DATABASE_URL = os.getenv("DATABASE_URL")

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

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    try:
        full_name = validate_name(data.get("full_name"))
        province = validate_location(data.get("province"), "province")
        district = validate_location(data.get("district"), "district")
        constituency = validate_location(data.get("constituency"), "constituency")
        phone = normalize_phone(data.get("phone"))

    except ValueError as e:
        return {"error": str(e)}, 400

    # Now safe to store
    # insert into DB here

    return {"message": "Registered successfully"}



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

@app.route('/approve/<int:id>', methods=['POST'])
def approve(id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("UPDATE applicants SET status='Approved' WHERE id=%s", (id,))
    conn.commit()

    cur.close()
    conn.close()

    return '', 204


@app.route('/reject/<int:id>', methods=['POST'])
def reject(id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("UPDATE applicants SET status='Rejected' WHERE id=%s", (id,))
    conn.commit()

    cur.close()
    conn.close()

    return '', 204

# ==============================
# ADD APPLICANT
# ==============================

@app.route("/add_applicant")
def add_applicant():
    return render_template("applicant.html")


# ==============================
# VOTER TABULATION
# ==============================
import psycopg2


@app.route("/voter_tabulation")
def voter_tabulation():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT province, constituency, polling_station,
                   pf_votes, upnd_votes, other_votes
            FROM polling_station_results
            ORDER BY province, constituency
        """)
        rows = cur.fetchall()

        results = []
        pf_total = 0
        upnd_total = 0
        other_total = 0

        for r in rows:
            results.append({
                "province": r[0],
                "constituency": r[1],
                "polling_station": r[2],
                "pf_votes": r[3] or 0,
                "upnd_votes": r[4] or 0,
                "other_votes": r[5] or 0
            })
            pf_total += r[3] or 0
            upnd_total += r[4] or 0
            other_total += r[5] or 0

        margin = pf_total - upnd_total

        return render_template("Full_Tabulation.html",
                               results=results,
                               pf_total=pf_total,
                               upnd_total=upnd_total,
                               other_total=other_total,
                               margin=margin)
    finally:
        cur.close()
        conn.close()

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
def agent_vote_send():
    incoming_msg = request.form.get("Body")
    sender = request.form.get("From")

    msg = incoming_msg.strip().upper()

    conn = get_db()
    cur = conn.cursor()

    # Verify agent
    cur.execute("""
        SELECT agent_id, province, constituency, polling_station
        FROM agents
        WHERE phone=%s AND active=TRUE
    """, (sender,))
    agent = cur.fetchone()

    if not agent:
        return jsonify({"reply": "Unauthorized agent."})

    agent_id, province, constituency, polling_station = agent

    # 🔴 RESULT SUBMISSION COMMAND
    if msg.startswith("RESULT"):
        try:
            parts = msg.split()

            pf_votes = int(parts[1])
            upnd_votes = int(parts[2])
            other_votes = int(parts[3]) if len(parts) > 3 else 0

            # Save results
            cur.execute("""
                INSERT INTO polling_station_results
                (agent_id, province, constituency, polling_station, pf_votes, upnd_votes, other_votes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (agent_id, province, constituency, polling_station, pf_votes, upnd_votes, other_votes))

            conn.commit()

            reply = f"Results received for {polling_station}. PF:{pf_votes} UPND:{upnd_votes}"

        except:
            reply = "Invalid format. Use: RESULT PF UPND OTHER"

    # 🔴 EXISTING BROADCAST COMMAND
    elif msg == "SEND VOTES":
        recipients = send_votes_for_constituency(constituency)
        reply = f"Broadcast sent to {recipients} members."

    else:
        reply = "Unknown command. Use RESULT or SEND VOTES."

    cur.close()
    conn.close()

    return jsonify({"reply": reply})

# ==============================
# BROADCAAST
# ==============================

@app.route('/broadcast', methods=['POST'])
def broadcast():

    # Accept both JSON and form data
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

    if not message:
        return jsonify({"error": "Message is required"}), 400

    whatsapp_sent = 0
    telegram_sent = 0

    import time

    # ==========================================
    # 🎯 DIRECT MESSAGE MODE (OVERRIDES FILTERS)
    # ==========================================
    if chat_id or phone:

        if phone:
            try:
                send_whatsapp_message(phone, message)
                whatsapp_sent += 1
            except Exception as e:
                print(f"WA failed {phone}: {e}")

        if chat_id:
            try:
                send_telegram_message(chat_id, message)
                telegram_sent += 1
            except Exception as e:
                print(f"TG failed {chat_id}: {e}")

        return jsonify({
            "status": "direct_sent",
            "whatsapp_sent": whatsapp_sent,
            "telegram_sent": telegram_sent,
            "chat_id": chat_id,
            "phone": phone
        }), 200

    # ==========================================
    # 📡 BROADCAST MODE (FILTERS)
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

        # WhatsApp
        if phone:
            try:
                send_whatsapp_message(phone, message)
                whatsapp_sent += 1
            except Exception as e:
                print(f"WA failed {phone}: {e}")

        # Telegram
        if chat_id:
            try:
                send_telegram_message(chat_id, message)
                telegram_sent += 1
            except Exception as e:
                print(f"TG failed {chat_id}: {e}")

        time.sleep(0.1)  # ⚠️ Reduced delay (1s is too slow at scale)

    cur.close()
    conn.close()

    return jsonify({
        "status": "broadcast_sent",
        "whatsapp_sent": whatsapp_sent,
        "telegram_sent": telegram_sent,
        "total_targeted": len(rows)
    }), 200
    
# ==============================
# LIVE STATS
# ==============================

@app.route("/live_stats")
def live_stats():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            COALESCE(SUM(pf_votes),0),
            COALESCE(SUM(upnd_votes),0)
        FROM polling_station_results
    """)

    pf, upnd = cur.fetchone()

    margin = pf - upnd

    if pf > upnd:
        status = "Winning"
    elif pf < upnd:
        status = "Losing"
    else:
        status = "Tied"

    cur.close()
    conn.close()

    return jsonify({
        "pf": pf,
        "upnd": upnd,
        "margin": margin,
        "status": status
    })

# ==============================
# MAP DATA
# ==============================

@app.route("/map_data")
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
def dashboard():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM members")
    total = cur.fetchone()[0]

    cur.execute("""
    SELECT province, COUNT(*)
    FROM members
    GROUP BY province
    """)

    provinces = cur.fetchall()

    cur.execute("""
        SELECT 
            COALESCE(SUM(pf_votes),0),
            COALESCE(SUM(upnd_votes),0),
            COALESCE(SUM(other_votes),0)
        FROM polling_station_results
    """)
    pf_total, upnd_total, other_total = cur.fetchone()

    margin = pf_total - upnd_total
    status = "Winning" if pf_total > upnd_total else "Losing"

    cur.close()
    conn.close()

    system_status = {
        "telegram": "OK",
        "qr": "",
        "database": "Connected",
        "server": "Running"
    }

    return render_template(
        "index.html",
        total_members=total,
        provinces=provinces,
        status=system_status
    )

# ==============================
# POLLING INTELLIGENCE
# ==============================

@app.route("/polling_intelligence")
def polling_intelligence():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT polling_station, COUNT(*)
        FROM members
        GROUP BY polling_station
        ORDER BY COUNT(*) DESC
    """)

    stations = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "polling_intelligence.html",
        stations=stations
    )

# ==============================
# ANALYTICS DASHBOARD
# ==============================

@app.route("/analytics")
def analytics():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT province, COUNT(*)
        FROM members
        GROUP BY province
        ORDER BY COUNT(*) DESC
    """)

    provinces = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "analytics.html",
        provinces=provinces
    )

# ==============================
# AGENTS LIST
# ==============================

@app.route("/agents", methods=["GET", "POST"])
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
