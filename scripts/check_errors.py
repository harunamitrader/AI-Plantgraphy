import sqlite3
import os

db_path = 'data/plants.sqlite'
if not os.path.exists(db_path):
    print(f"Error: {db_path} does not exist.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, status, error_message FROM observations WHERE status = 'analysis_failed' LIMIT 5;")
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, Status: {row[1]}, Error: {row[2]}")
finally:
    conn.close()
