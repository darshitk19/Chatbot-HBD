# db/db.py
import sqlite3
import math
import re
from datetime import datetime
from typing import List, Dict

from db.config import DB_PATH
from ranking.ml_ranker import load_ranker


# ============================================================
# Optional ML ranker (used only if present & compatible)
# ============================================================
ML_MODEL = load_ranker()


# ============================================================
# Configuration
# ============================================================
INFO_FIELDS = [
    "website",
    "phone_number",
    "address",
    "category",
    "subcategory",
    "city",
    "state",
]


# ============================================================
# Database Access
# ============================================================
def run_sql(sql: str) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return rows


# ============================================================
# Utilities
# ============================================================
def tokenize(text: str) -> set:
    return set(re.findall(r"\w+", text.lower())) if text else set()


def info_completeness_score(r: Dict) -> float:
    """
    Normalized info completeness score (0 → 1)
    """
    filled = sum(
        1 for f in INFO_FIELDS
        if r.get(f) and str(r.get(f)).strip()
    )
    return filled / len(INFO_FIELDS)


# ============================================================
# Ranking Logic (Customer + Business Friendly)
# ============================================================
def rank_results(
    rows: List[Dict],
    query: str = "",
    top_n: int = 10
) -> List[Dict]:
    """
    Unified ranking logic:

    CUSTOMER SEARCH:
    - Rating-first ranking
    - Popularity confidence
    - Query relevance

    BUSINESS QUALITY:
    - Info completeness boost
    - Freshness boost

    OPTIONAL:
    - ML ranker if available (safe fallback)
    """

    now = datetime.utcnow()
    ranked = []
    seen = set()
    query_tokens = tokenize(query)

    # ------------------------------
    # Feature extraction
    # ------------------------------
    for r in rows:
        # -------- remove permanently closed --------
        text = f"{r.get('name','')} {r.get('address','')}".lower()
        if "permanently closed" in text:
            continue

        # -------- deduplicate --------
        dedup_key = (
            (r.get("name") or "").lower().strip(),
            (r.get("address") or "").lower().strip()
        )
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # -------- base values --------
        rating = r.get("reviews_average")
        reviews = r.get("reviews_count") or 0

        # Neutral default for local businesses
        if rating is None:
            rating = 3.5

        # =====================================================
        # REQUIRED CORE FORMULA (YOU ASKED FOR THIS)
        # =====================================================
        base_score = rating * 0.75 + reviews * 0.002

        # -------- info completeness boost --------
        info_ratio = info_completeness_score(r)
        info_boost = info_ratio * 0.5   # safe, non-dominant

        # -------- freshness boost --------
        freshness_boost = 0.0
        try:
            created = datetime.fromisoformat(r.get("created_at"))
            if (now - created).days <= 180:
                freshness_boost = 0.1
        except Exception:
            pass

        # -------- query relevance (for search) --------
        relevance = 0.0
        if query_tokens:
            searchable_text = f"""
                {r.get('name','')}
                {r.get('category','')}
                {r.get('subcategory','')}
                {r.get('area','')}
            """
            relevance = (
                len(tokenize(searchable_text) & query_tokens)
                / max(len(query_tokens), 1)
            )

        # -------- popularity (log-scaled) --------
        popularity = math.log1p(reviews)

        # -------- ML feature vector --------
        features = [
            base_score,
            info_ratio,
            relevance,
            popularity
        ]

        r["features"] = features
        r["rating"] = rating
        r["reviews"] = reviews
        r["info_score"] = round(info_ratio, 3)

        # -------- final heuristic score --------
        r["score"] = round(
            base_score +
            info_boost +
            freshness_boost +
            relevance * 0.3,
            3
        )

        ranked.append(r)

    if not ranked:
        return []

    # ------------------------------
    # ML scoring (optional, safe)
    # ------------------------------
    if ML_MODEL:
        X = [r["features"] for r in ranked]

        try:
            scores = ML_MODEL.predict(X)
        except ValueError:
            # feature mismatch protection
            expected = getattr(ML_MODEL, "n_features_in_", None)
            if expected:
                X_fixed = [x[:expected] for x in X]
                scores = ML_MODEL.predict(X_fixed)
            else:
                scores = None

        if scores is not None:
            for r, s in zip(ranked, scores):
                r["score"] = float(s)

    # ------------------------------
    # Final stable ranking
    # ------------------------------
    ranked.sort(
        key=lambda x: (
            x["score"],       # overall quality
            x["info_score"],  # better profiles win ties
            x["rating"],      # higher stars
            x["reviews"],     # more confidence
        ),
        reverse=True
    )

    return ranked[:top_n]
