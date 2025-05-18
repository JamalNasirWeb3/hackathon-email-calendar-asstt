import sqlite3

def init_db():
    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant TEXT,
            date TEXT,
            time TEXT,
            status TEXT,
            link TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_meeting(participant, date, time, status, link):
    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO meetings (participant, date, time, status, link)
        VALUES (?, ?, ?, ?, ?)
    """, (participant, date, time, status, link))
    conn.commit()
    conn.close()

def fetch_meetings(month=None, participant=None):
    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()
    query = "SELECT participant, date, time, status, link FROM meetings WHERE 1=1"
    params = []

    if month:
        query += " AND strftime('%m', date) = ?"
        params.append(month.zfill(2))
    if participant:
        query += " AND LOWER(participant) LIKE ?"
        params.append(f"%{participant.lower()}%")

    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results
