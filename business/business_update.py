import sqlite3
from db.config import DB_PATH

ALLOWED_FIELDS = [
    "name",
    "address",
    "phone_number",
    "website",
    "category",
    "subcategory",
    "area",
    "city",
    "state",
]

def update_business(business_id: int = None, updates: dict = None, phone_number: str = None):
    """
    Update business details directly in the existing record.
    Can update by business_id or by phone_number if id is not available.
    Updates all provided fields (including empty strings to clear fields).
    Only updates fields that are in ALLOWED_FIELDS.
    """
    if updates is None:
        return False
    
    # Filter to allowed fields only, preserve all values (including empty strings)
    # Convert None to empty string for consistency
    filtered_updates = {}
    for k, v in updates.items():
        if k in ALLOWED_FIELDS:
            if v is None:
                filtered_updates[k] = ""
            elif isinstance(v, str):
                filtered_updates[k] = v.strip()
            else:
                filtered_updates[k] = v

    if not filtered_updates:
        return False

    fields = [f"{k} = ?" for k in filtered_updates]
    values = list(filtered_updates.values())

    # Determine WHERE clause - use ID if available, otherwise use phone number
    if business_id is not None:
        where_clause = "WHERE id = ?"
        values.append(business_id)
    elif phone_number:
        where_clause = "WHERE phone_number LIKE ?"
        values.append(f"%{phone_number}%")
    else:
        return False

    query = f"""
        UPDATE google_maps_listings
        SET {', '.join(fields)}
        {where_clause}
    """

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(query, values)
        rows_affected = cur.rowcount
        conn.commit()
        return rows_affected > 0
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
