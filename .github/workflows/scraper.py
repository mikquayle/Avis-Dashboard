#!/usr/bin/env python3
"""
scraper.py — pulls the Google rating for a business and appends it to data/ratings.json
Runs via GitHub Actions every 30 minutes.

Dependencies: pip install requests beautifulsoup4
"""

import json
import os
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Edit these two values to target your specific business listing.
BUSINESS_NAME = "Avis"
GOOGLE_MAPS_URL = os.environ.get(
    "GOOGLE_MAPS_URL",
    # Paste your Avis location's Google Maps URL here as the fallback:
    "https://www.google.com/maps/place/Avis+Car+Rental"
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "ratings.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
# ─────────────────────────────────────────────────────────────────────────────


def fetch_rating(url: str) -> float | None:
    """Return the star rating as a float, or None if scraping fails."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[scraper] HTTP error: {exc}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Google embeds the rating in several possible spots — try them all.
    selectors = [
        {"attrs": {"data-attrid": "kc:/collection/knowledge_panels/local_reviewable:star_score"}},
        {"class": "Aq14fc"},   # Maps embed rating span
        {"class": "MW4etd"},   # Another common class
    ]
    for sel in selectors:
        tag = soup.find(attrs=sel) if "attrs" in sel else soup.find(class_=sel.get("class"))
        if tag and tag.text.strip():
            try:
                return float(tag.text.strip().replace(",", "."))
            except ValueError:
                continue

    # Fallback: search for a pattern like "4.3 stars"
    import re
    match = re.search(r'"(\d\.\d)\s*stars?"', resp.text)
    if match:
        return float(match.group(1))

    print("[scraper] Could not parse rating from page.")
    return None


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"business_name": BUSINESS_NAME, "last_updated": "", "current_rating": None, "history": []}


def save_data(data: dict) -> None:
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[scraper] Saved → {DATA_FILE}")


def main() -> None:
    print(f"[scraper] Fetching rating for {BUSINESS_NAME} …")
    rating = fetch_rating(GOOGLE_MAPS_URL)

    if rating is None:
        print("[scraper] No rating found — aborting without writing.")
        return

    now = datetime.now(timezone.utc).isoformat()
    data = load_data()
    data["business_name"] = BUSINESS_NAME
    data["current_rating"] = rating
    data["last_updated"] = now
    data["history"].append({"timestamp": now, "rating": rating})

    # Keep last 500 data points so the file stays small
    data["history"] = data["history"][-500:]

    save_data(data)
    print(f"[scraper] Done — {BUSINESS_NAME}: {rating} ⭐  at {now}")


if __name__ == "__main__":
    main()
