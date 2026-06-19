import os
import json
import requests
from datetime import datetime

# Google Places API key from environment/secret
API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")

# Avis locations to track - add your Place IDs here
LOCATIONS = [
    {
        "name": "Avis Las Vegas Airport",
        "place_id": "ChIJa2-KsJjEyIARTJ5kR8JVkdI"
    },
    {
        "name": "Avis Las Vegas Downtown",
        "place_id": "ChIJOwg_06VPwokRYv534QaPC8g"
    },
    # Add more locations here as needed
]

DATA_FILE = "data/ratings.json"


def fetch_place_details(place_id):
    """Fetch rating and review count for a given Place ID."""
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,rating,user_ratings_total,formatted_address",
        "key": API_KEY,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    result = response.json()

    if result.get("status") != "OK":
        raise ValueError(f"Places API error: {result.get('status')} - {result.get('error_message', '')}")

    return result["result"]


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
        review_count = details.get("user_ratings_total")
        address = details.get("formatted_address", "")

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
