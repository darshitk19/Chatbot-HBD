def needs_sql(query: str) -> bool:
    keywords = [
        "best", "top", "near", "shop", "restaurant",
        "company", "companies", "service", "services",
        "hospital", "clinic", "seo", "digital"
    ]
    q = query.lower()
    return any(k in q for k in keywords)
