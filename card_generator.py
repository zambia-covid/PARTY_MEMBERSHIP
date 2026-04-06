import qrcode
from PIL import Image, ImageDraw, ImageFont

def generate_card(member_code,name):

    qr = qrcode.make(member_code)
    qr.save("qr.png")

    card = Image.new("RGB",(600,350),"white")

    draw = ImageDraw.Draw(card)

    font = ImageFont.load_default()

    draw.text((200,50),"MEMBERSHIP CARD",(0,0,0),font=font)
    draw.text((200,120),name,(0,0,0),font=font)
    draw.text((200,180),member_code,(0,0,0),font=font)

    qr_img = Image.open("qr.png").resize((150,150))

    card.paste(qr_img,(30,150))

    file_name = f"{member_code}.png"

    card.save(file_name)

    return file_name