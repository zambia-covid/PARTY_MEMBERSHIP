from flask import Blueprint, jsonify
from flask_login import login_required
from db import get_db

# ✅ THIS LINE WAS MISSING (CRITICAL)
analytics_bp = Blueprint("analytics", __name__)


# =========================
# TURNOUT TARGETS
# =========================
@analytics_bp.route("/api/turnout_targets")
@login_required
def turnout_targets():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            m.polling_station,
            COUNT(m.membership_id) AS members,
            COALESCE(SUM(r.pf_votes + r.upnd_votes),0) AS votes
        FROM members m
        LEFT JOIN polling_station_results r
            ON m.polling_station = r.polling_station
        GROUP BY m.polling_station
    """)

    results = []

    for station, members, votes in cur.fetchall():

        gap = members - votes

        if gap > 50:
            priority = "CRITICAL"
        elif gap > 20:
            priority = "HIGH"
        else:
            priority = "LOW"

        results.append({
            "station": station,
            "members": members,
            "votes": votes,
            "gap": gap,
            "priority": priority
        })

    cur.close()
    conn.close()

    return jsonify(results)
