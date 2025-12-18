def extract_city(query: str):
    q = query.lower()
    if " in " in q:
        return q.split(" in ")[-1].strip()
    return None


def generate_sql(query: str) -> str:
    q = query.lower()
    city = extract_city(q)

    stop_words = {
        "best", "top", "near", "in", "for",
        "the", "of", "business", "businesses",
        "service", "services"
    }

    keywords = [
        w for w in q.split()
        if len(w) > 2
        and w not in stop_words
        and w != city
    ]

    if not keywords:
        keywords = [q]

    service_conditions = []
    for k in keywords:
        service_conditions.append(
            f"""
            LOWER(name) LIKE '%{k}%'
            OR LOWER(category) LIKE '%{k}%'
            OR LOWER(subcategory) LIKE '%{k}%'
            """
        )

    service_clause = " OR ".join(service_conditions)

    city_clause = ""
    if city:
        city_clause = f"AND LOWER(city) = '{city}'"

    return f"""
    SELECT DISTINCT *
    FROM google_maps_listings
    WHERE ({service_clause})
      {city_clause}
      AND LOWER(name || ' ' || IFNULL(address,'')) NOT LIKE '%permanently closed%'
    LIMIT 200
    """.strip()
