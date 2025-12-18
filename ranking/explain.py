def explain_business(r):
    reasons = []

    rating = r.get("reviews_average")
    if rating is None:
        rating = 0

    reviews = r.get("reviews_count", 0) or 0
    info_score = r.get("info_score", 0) or 0

    if rating >= 4.5:
        reasons.append("excellent ratings")
    if reviews >= 300:
        reasons.append("high popularity")
    if info_score >= 0.8:
        reasons.append("complete profile")
    if reviews < 50:
        reasons.append("new/local business")

    return ", ".join(reasons) if reasons else "relevant match"
