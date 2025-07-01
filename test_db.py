import pymysql

print("🔵 Trying XAMPP MySQL with PyMySQL...")

try:
    print("🟡 Step 1: Starting connection...")
    conn = pymysql.connect(
        host="127.0.0.1",
        user="root",
        password="",
        port=3306,  # Change if XAMPP is using 3307
        database="run_events",
        connect_timeout=5
    )
    print("🟢 Step 2: Connection established.")
    cursor = conn.cursor()
    print("🟢 Step 3: Cursor created.")
    cursor.execute("SHOW TABLES;")
    tables = cursor.fetchall()
    print("✅ Connected to XAMPP MySQL via PyMySQL! Tables:", tables)
except Exception as e:
    print("❌ Connection failed:", e)
