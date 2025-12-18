def get_update_suggestions(business: dict):
    suggestions = []

    if not business.get("website"):
        suggestions.append("Add a website to improve trust")

    if not business.get("phone_number"):
        suggestions.append("Add a phone number so customers can contact you")

    if not business.get("address"):
        suggestions.append("Add a complete address")

    reviews_count = business.get("reviews_count", 0) or 0
    rating = business.get("reviews_average")
    if rating is None:
        rating = 0

    if reviews_count < 5:
        suggestions.append("Get more customer reviews")

    if rating < 4:
        suggestions.append("Improve service quality to increase ratings")

    if not business.get("subcategory"):
        suggestions.append("Add a subcategory for better visibility")

    return suggestions
