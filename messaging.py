import os
import requests
from twilio.rest import Client

def send_sms(phone, message):

    url = "https://api.talkingafrica.com/v1/send_sms"

    requests.post(url, json={
        "api_key": os.getenv("TA_API_KEY"),
        "username": os.getenv("TA_USERNAME"),
        "to": phone,
        "message": message
    })

def send_whatsapp(phone, message):

    client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

    client.messages.create(
        body=message,
        from_=os.getenv("TWILIO_WHATSAPP_NUMBER"),
        to=f"whatsapp:{phone}"
    )
