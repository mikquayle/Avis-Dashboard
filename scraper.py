#!/usr/bin/env python3
import json, os
from datetime import datetime, timezone
import requests

BUSINESS_NAME    = "Avis Car Rental - Las Vegas Airport"
LOCATIONS = [
    {
        "name": "Avis Car Rental - McCarran Airport",
        "place_id": "ChIJiaIDn2DPyIARUwzDWSzAOrc"
    },
    # Add more locations here as needed
]
API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
if not API_KEY:
    raise ValueError("GOOGLE_PLACES_API_KEY secret is not set in GitHub Actions")
DATA_FILE        = os.path.join(os.path.dirname(__file__), "data", "ratings.json")

def fetch_rating():
    url = "https://places.googleapis.com/v1/places/" + PLACE_ID
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "rating,userRatingCount,displayName"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    print(f"[scraper] API response: {data}")
    return data.get("rating"), data.get("userRatingCount")

def main():
    rating, review_count = fetch_rating()
    if rating is None:
        print("[scraper] No rating returned — exiting.")
        return
    now = datetime.now(timezone.utc).isoformat()
    data = json.load(open(DATA_FILE)) if os.path.exists(DATA_FILE) else {"business_name": BUSINESS_NAME, "last_updated": "", "current_rating": None, "review_count": None, "history": []}
    data.update({"business_name": BUSINESS_NAME, "current_rating": rating, "review_count": review_count, "last_updated": now})
    data["history"] = (data["history"] + [{"timestamp": now, "rating": rating, "review_count": review_count}])[-500:]
    json.dump(data, open(DATA_FILE, "w"), indent=2)
    print(f"[scraper] Done — {rating} ⭐ ({review_count} reviews) at {now}")

if __name__ == "__main__":
    main()
