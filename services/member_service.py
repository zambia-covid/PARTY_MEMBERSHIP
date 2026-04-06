import random
from database.db import get_connection


def generate_membership_id():

    conn = get_connection()
    cur = conn.cursor()

    while True:

        number = random.randint(1000000,9999999)
        member_id = f"PFP{number}"

        cur.execute(
            "SELECT 1 FROM members WHERE membership_id=%s",
            (member_id,)
        )

        if not cur.fetchone():
            break

    cur.close()
    conn.close()

    return member_id


def save_member(name, province, constituency, phone, chat_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT membership_id FROM members WHERE chat_id=%s",
        (chat_id,)
    )

    if cur.fetchone():
        cur.close()
        conn.close()
        return "DUPLICATE"

    cur.execute("""
        INSERT INTO members
        (full_name,province,constituency,phone,chat_id,status)
        VALUES (%s,%s,%s,%s,%s,'Active')
    """,(name,province,constituency,phone,chat_id))

    conn.commit()

    cur.close()
    conn.close()

    return "SUCCESS"


def update_member_id(phone, member_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE members SET membership_id=%s WHERE phone=%s",
        (member_id,phone)
    )

    conn.commit()

    cur.close()
    conn.close()