import sqlite3
from datetime import datetime

from db.config import DB_PATH


def add_business(
    name: str,
    address: str,
    phone_number: str = "",
    website: str = "",
    category: str = "",
    subcategory: str = "",
    city: str = "",
    state: str = "",
    area: str = "",
    owner_email: str | None = None,
) -> int:
    """
    Insert a new business into google_maps_listings and return its new ID.
    Minimal required fields are name and address; everything else is optional.
    """
    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Idempotency / uniqueness: if a business with same name + full address + phone already exists,
    # return its ID instead of inserting a duplicate.
    cur.execute(
        """
        SELECT id FROM google_maps_listings
        WHERE LOWER(name) = LOWER(?)
          AND LOWER(IFNULL(address,'')) = LOWER(?)
          AND LOWER(IFNULL(area,'')) = LOWER(?)
          AND LOWER(IFNULL(city,'')) = LOWER(?)
          AND LOWER(IFNULL(state,'')) = LOWER(?)
          AND LOWER(IFNULL(phone_number,'')) = LOWER(?)
        """,
        (name, address or "", area or "", city or "", state or "", phone_number or ""),
    )
    row = cur.fetchone()
    if row and row[0] is not None:
        existing_id = row[0]
        try:
            existing_id = int(existing_id)
        except (TypeError, ValueError):
            pass
        conn.close()
        return existing_id

    base_values = (
        name,
        address,
        website or "",
        phone_number or "",
        0,          # reviews_count
        None,       # reviews_average
        category or "",
        subcategory or "",
        city or "",
        state or "",
        area or "",
        created_at,
    )

    # Prefer schema with owner_email; fallback to older schema if column not present
    try:
        cur.execute(
            """
            INSERT INTO google_maps_listings
            (name, address, website, phone_number,
             reviews_count, reviews_average,
             category, subcategory, city, state, area, created_at, owner_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            base_values + (owner_email or "",),
        )
    except sqlite3.OperationalError:
        # old schema without owner_email
        cur.execute(
            """
            INSERT INTO google_maps_listings
            (name, address, website, phone_number,
             reviews_count, reviews_average,
             category, subcategory, city, state, area, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            base_values,
        )

    conn.commit()
    new_id = cur.lastrowid
    
    # If lastrowid is 0 or None, fetch the ID we just inserted
    if not new_id or new_id == 0:
        cur.execute(
            """
            SELECT id FROM google_maps_listings
            WHERE LOWER(name) = LOWER(?)
              AND LOWER(IFNULL(address,'')) = LOWER(?)
              AND LOWER(IFNULL(area,'')) = LOWER(?)
              AND LOWER(IFNULL(city,'')) = LOWER(?)
              AND LOWER(IFNULL(state,'')) = LOWER(?)
              AND LOWER(IFNULL(phone_number,'')) = LOWER(?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (name, address or "", area or "", city or "", state or "", phone_number or ""),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            try:
                new_id = int(row[0])
            except (TypeError, ValueError):
                pass
    
    conn.close()

    return new_id if new_id else None


