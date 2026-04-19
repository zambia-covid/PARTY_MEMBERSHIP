from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_strategy(context):

    prompt = f"""
Constituency: {context}
Give 1 short political action.
"""

    res = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    return res.output_text.strip()
