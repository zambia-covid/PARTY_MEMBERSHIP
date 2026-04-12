import os
import csv
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

with open('contacts.csv', 'r', encoding='utf-8') as file:
    reader = csv.DictReader(file)
    for row in reader:
        cur.execute("""
            INSERT INTO contacts (name, phone, ward, constituency, tag)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (phone) DO NOTHING;
        """, (
            row['Name'],
            row['Phone'],
            row['Ward'],
            row['Constituency'],
            row['Tag']
        ))

conn.commit()
cur.close()
conn.close()

print("Import complete.")