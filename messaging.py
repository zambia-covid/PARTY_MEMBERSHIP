import os
import requests
from twilio.rest import Client

def send_sms(phone, message):
    try:
        requests.post(
            "https://api.talkingafrica.com/v1/send_sms",
            json={
                "api_key": os.getenv("TA_API_KEY"),
                "username": os.getenv("TA_USERNAME"),
                "to": phone,
                "message": message,
                "sender_id": os.getenv("TA_SENDER_ID")
            },
            timeout=10
        )
    except Exception as e:
        print("SMS error:", e)


def send_whatsapp(phone, message):
    try:
        Client(
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN")
        ).messages.create(
            body=message,
            from_=os.getenv("TWILIO_WHATSAPP_NUMBER"),
            to=f"whatsapp:{phone}"
        )
    except Exception as e:
        print("WA error:", e)


def send_telegram(chat_id, message):
    try:
        requests.post(
            f"https://api.telegram.org/bot{os.getenv('BOT_TOKEN')}/sendMessage",
            data={"chat_id": chat_id, "text": message},
            timeout=10
        )
    except Exception as e:
        print("TG error:", e)