import os
import math
import requests
from dotenv import load_dotenv

load_dotenv()
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

def search_online(query):
    r = requests.get(
        "https://serpapi.com/search",
        params={
            "engine": "google_maps",
            "q": query,
            "api_key": SERPAPI_KEY
        },
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("local_results", [])

def rank_online_results(results):
    def score(r):
        return (
            (r.get("rating", 0) or 0) * 0.6 +
            math.log1p(r.get("reviews", 0) or 0) * 0.4
        )
    return sorted(results, key=score, reverse=True)
