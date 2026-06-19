#!/usr/bin/env python3
import json, os, re
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

BUSINESS_NAME = "Avis"
GOOGLE_MAPS_URL = os.environ.get(
    "GOOGLE_MAPS_URL",
    "https://www.google.com/maps/place/Avis+Car+Rental"
)
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "ratings.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_rating(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[scraper] HTTP error: {exc}")
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    for cls in ["Aq14fc", "MW4etd"]:
        tag = soup.find(class_=cls)
        if tag and tag.text.strip():
            try: return float(tag.text.strip().replace(",", "."))
            except ValueError: continue
    match = re.search(r'"(\d\.\d)\s*stars?"', resp.text)
    if match: return float(match.group(1))
    print("[scraper] Could not parse rating.")
    return None

def main():
    rating = fetch_rating(GOOGLE_MAPS_URL)
    if rating is None:
        print("[scraper] No rating found — exiting.")
        return
    now = datetime.now(timezone.utc).isoformat()
    data = json.load(open(DATA_FILE)) if os.path.exists(DATA_FILE) else {"business_name": BUSINESS_NAME, "last_updated": "", "current_rating": None, "history": []}
    data.update({"business_name": BUSINESS_NAME, "current_rating": rating, "last_updated": now})
    data["history"] = (data["history"] + [{"timestamp": now, "rating": rating}])[-500:]
    json.dump(data, open(DATA_FILE, "w"), indent=2)
    print(f"[scraper] {BUSINESS_NAME}: {rating} ⭐ at {now}")

if __name__ == "__main__":
    main()
