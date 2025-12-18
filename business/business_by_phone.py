import sqlite3
from db.config import DB_PATH

def get_businesses_by_phone(phone: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM google_maps_listings
        WHERE phone_number LIKE ?
        """,
        (f"%{phone}%",)
    )

    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    conn.close()

    return [dict(zip(cols, r)) for r in rows]
