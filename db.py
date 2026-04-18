import os
import psycopg2

def get_db():
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        return psycopg2.connect(
            host="localhost",
            database="membership_db",
            user="postgres",
            password=os.getenv("DB_PASSWORD")
        )

    return psycopg2.connect(db_url, sslmode="require")