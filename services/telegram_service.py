import requests
from config import Config


def send_message(chat_id,text):

    url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendMessage"

    requests.post(url,json={
        "chat_id":chat_id,
        "text":text
    })


def send_photo(chat_id,photo_path):

    url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendPhoto"

    with open(photo_path,"rb") as photo:

        requests.post(
            url,
            data={"chat_id":chat_id},
            files={"photo":photo}
        )