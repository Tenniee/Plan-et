import pymysql

# 🔵 Function to get a fresh DB connection and cursor
def get_cursor():
    try:
        # Establish a new connection
        conn = pymysql.connect(
            host="127.0.0.1",
            user="root",
            password="",
            port=3306,
            database="run_events",
            connect_timeout=5
        )

        cursor = conn.cursor()  # ✅ define the cursor here
        cursor.execute("SELECT DATABASE();")
        print("✅ Connected to DB:", cursor.fetchone())

        # Return both conn and cursor so they can be closed in the endpoint
        return conn, cursor

    except Exception as e:
        print("❌ Failed to connect to DB:", e)
        raise
