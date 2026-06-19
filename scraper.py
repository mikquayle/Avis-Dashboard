import os
import json
import requests
from datetime import datetime

# Google Places API key from environment/secret
API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")

# Avis locations to track
LOCATIONS = [
    {
        "name": "Avis Car Rental - McCarran Airport",
        "place_id": "ChIJiaIDn2DPyIARUwzDWSzAOrc"
    },
    # Add more locations here as needed
]

DATA_FILE = "data/ratings.json"


def fetch_place_details(place_id):
    """Fetch rating and review count using Places API (New)."""
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "displayName,rating,userRatingCount,formattedAddress",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    result = response.json()

    if "error" in result:
        raise ValueError(f"Places API error: {result['error'].get('message', 'Unknown error')}")

    return result


def load_existing_data():
    """Load existing ratings data if it exists."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"locations": {}, "history": {}}


def save_data(data):
    """Save updated ratings data."""
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def main():
    if not API_KEY:
        raise EnvironmentError("GOOGLE_PLACES_API_KEY secret is not set.")

    data = load_existing_data()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    for location in LOCATIONS:
        place_id = location["place_id"]
        name = location["name"]

        print(f"Fetching: {name} ({place_id})")
        details = fetch_place_details(place_id)

        rating = details.get("rating")
        review_count = details.get("userRatingCount")
        address = details.get("formattedAddress", "")

        # Update current snapshot
        data["locations"][place_id] = {
            "name": name,
            "address": address,
            "rating": rating,
            "review_count": review_count,
            "last_updated": today,
        }

        # Append to history
        if place_id not in data["history"]:
            data["history"][place_id] = []

        # Avoid duplicate entries for same day
        existing_dates = [h["date"] for h in data["history"][place_id]]
        if today not in existing_dates:
            data["history"][place_id].append({
                "date": today,
                "rating": rating,
                "review_count": review_count,
            })

        print(f"  → {rating} ⭐ ({review_count} reviews)")

    save_data(data)
    print(f"\n✅ Data saved to {DATA_FILE}")


if __name__ == "__main__":
    main()
