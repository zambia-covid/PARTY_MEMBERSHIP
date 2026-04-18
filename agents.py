from flask import Blueprint, request, redirect
from flask_login import login_required
from db import get_db
from messaging import send_whatsapp

agents_bp = Blueprint("agents", __name__)

# ======================
# SUBMIT RESULTS
# ======================
@agents_bp.route("/submit_results", methods=["POST"])
@login_required
def submit_results():

    pf = int(request.form.get("pf", 0))
    upnd = int(request.form.get("upnd", 0))
    station = request.form.get("station")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO polling_station_results
        (polling_station, pf_votes, upnd_votes)
        VALUES (%s,%s,%s)
    """, (station, pf, upnd))

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/")


# ======================
# MOBILIZE
# ======================
@agents_bp.route("/mobilize/<station>")
@login_required
def mobilize(station):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT phone FROM members
        WHERE polling_station=%s
    """, (station,))

    phones = cur.fetchall()

    count = 0

    for p in phones:
        try:
            send_whatsapp(p[0], f"⚠️ Go vote now at {station}")
            count += 1
        except:
            pass

    cur.close()
    conn.close()

    return f"Mobilized {count}"