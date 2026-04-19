from flask import Blueprint, jsonify
from db import get_db

analytics_bp = Blueprint("analytics", __name__)

@analytics_bp.route("/api/live_dashboard")
def live_dashboard():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT constituency,
               SUM(pf_votes),
               SUM(upnd_votes)
        FROM polling_station_results
        GROUP BY constituency
    """)

    data = []

    for c, pf, upnd in cur.fetchall():
        margin = pf - upnd

        status = "WIN" if margin > 0 else "LOSE"

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
