import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def classify_voter(member):
    try:
        prompt = f"""
Classify this voter:
Name: {member.get("full_name")}
Province: {member.get("province")}
Constituency: {member.get("constituency")}
Ward: {member.get("ward")}
Return ONLY: STRONG, LEANING, WEAK
"""
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        return res.output_text.strip().upper()
    except:
        return "UNKNOWN"


def generate_message(context):
    try:
        prompt = f"""
Create a short political campaign message.
Province: {context.get("province")}
Constituency: {context.get("constituency")}
Ward: {context.get("ward")}
Under 40 words.
"""
        res = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
        return res.output_text.strip()
    except:
        return "Stay engaged. Your vote matters."