from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_strategy(context):

    res = client.responses.create(
        model="gpt-5-mini",
        input=f"Give short political strategy for: {context}"
    )

    return res.output_text.strip()
