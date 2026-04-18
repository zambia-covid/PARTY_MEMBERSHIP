from flask import Blueprint, jsonify
from flask_login import login_required
from db import get_db

analytics_bp = Blueprint("analytics", __name__)

# ======================
# DECISION ENGINE
# ======================
def decision_engine(members, voters, pf, upnd):
    penetration = (members / voters * 100) if voters else 0

    if pf > upnd and penetration >= 40:
        return "WIN"
    elif pf < upnd and penetration < 30:
        return "LOSE"
    return "TOSS-UP"


# ======================
# LIVE DASHBOARD
# ======================
@analytics_bp.route("/api/live_dashboard")
@login_required
def live_dashboard():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            c.constituency,
            c.province,
            COUNT(DISTINCT m.membership_id),
            c.total_voters,
            COALESCE(SUM(r.pf_votes),0),
            COALESCE(SUM(r.upnd_votes),0)
        FROM constituencies c
        LEFT JOIN members m ON m.constituency = c.constituency
        LEFT JOIN polling_station_results r ON r.constituency = c.constituency
        GROUP BY c.constituency, c.province, c.total_voters
    """)

    data = []

    for c, p, members, voters, pf, upnd in cur.fetchall():

        penetration = (members / voters * 100) if voters else 0
        margin = pf - upnd
        status = decision_engine(members, voters, pf, upnd)

        data.append({
            "constituency": c,
            "province": p,
            "members": members,
            "voters": voters,
            "pf": pf,
            "upnd": upnd,
            "margin": margin,
            "penetration": round(penetration, 2),
            "status": status
        })

    cur.close()
    conn.close()

    return jsonify(data)


# ======================
# TURNOUT TARGETS
# ======================
@analytics_bp.route("/api/turnout_targets")
@login_required
def turnout_targets():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            polling_station,
            COUNT(m.membership_id),
            COALESCE(SUM(r.pf_votes + r.upnd_votes),0)
        FROM members m
        LEFT JOIN polling_station_results r
        ON m.polling_station = r.polling_station
        GROUP BY polling_station
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