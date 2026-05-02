import os
import qrcode
from PIL import Image, ImageDraw, ImageFont


def generate_membership_card(full_name, province, constituency, member_id):

    print("🚀 GENERATING CARD:", member_id)

    # ==============================
    # PATH SETUP (UNIFIED)
    # ==============================
    base_dir = os.getcwd()
    card_dir = os.path.join(base_dir, "static", "cards")
    os.makedirs(card_dir, exist_ok=True)

    file_path = os.path.join(card_dir, f"{member_id}.png")

    # ==============================
    # QR CODE
    # ==============================
    qr = qrcode.make(member_id)
    qr_img = qr.resize((150, 150))

    # ==============================
    # CARD BASE
    # ==============================
    card = Image.new("RGB", (600, 350), "white")
    draw = ImageDraw.Draw(card)
    font = ImageFont.load_default()

    # ==============================
    # TEXT
    # ==============================
    draw.text((200, 40), "MEMBERSHIP CARD", fill=(0, 0, 0), font=font)
    draw.text((200, 100), f"Name: {full_name}", fill=(0, 0, 0), font=font)
    draw.text((200, 140), f"Province: {province}", fill=(0, 0, 0), font=font)
    draw.text((200, 180), f"Constituency: {constituency}", fill=(0, 0, 0), font=font)
    draw.text((200, 220), f"ID: {member_id}", fill=(0, 0, 0), font=font)

    # ==============================
    # PASTE QR
    # ==============================
    card.paste(qr_img, (30, 150))

    # ==============================
    # SAVE
    # ==============================
    card.save(file_path)

    print("✅ CARD SAVED:", file_path)

    return file_path
