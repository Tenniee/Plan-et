import pymysql
import os

from dotenv import load_dotenv

load_dotenv()

# 🔵 Function to get a fresh DB connection and cursor
def get_cursor():
    try:
        # Establish a new connection
        conn = pymysql.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )

        cursor = conn.cursor()  # ✅ define the cursor here
        cursor.execute("SELECT DATABASE();")
        print("✅ Connected to DB:", cursor.fetchone())

        # Return both conn and cursor so they can be closed in the endpoint
        return conn, cursor

    except Exception as e:
        print("❌ Failed to connect to DB:", e)
        raise
