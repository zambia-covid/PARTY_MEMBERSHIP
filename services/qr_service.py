import os
import qrcode

def generate_qr(member_id):

    folder = "static/qrcodes"
    os.makedirs(folder,exist_ok=True)

    file_path = f"{folder}/{member_id}.png"

    img = qrcode.make(member_id)
    img.save(file_path)

    return file_path