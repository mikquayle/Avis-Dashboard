import os
import json
import requests
from datetime import datetime

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")

LOCATIONS = [
    {
        "name": "Avis Car Rental - Harry Reid Airport",
        "search_query": "Avis Car Rental 7135 Gilespie St Las Vegas NV"
    },
]

DATA_FILE = "data/ratings.json"

def find_place_id(search_query):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.userRatingCount,places.formattedAddress",
    }
    body = {"textQuery": search_query}
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    result = response.json()
    print(f"  Search response: {result}")
    places = result.get("places", [])
    if not places:
        raise ValueError(f"No places found for query: {search_query}")
    return places[0]

def load_existing_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"locations": {}, "history": {}}

def save_data(data):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def main():
    if not API_KEY:
        raise EnvironmentError("GOOGLE_PLACES_API_KEY secret is not set.")

    data = load_existing_data()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    for location in LOCATIONS:
        name = location["name"]
        search_query = location["search_query"]
        print(f"Searching: {name}")

        place = find_place_id(search_query)
        place_id = place.get("id")
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        address = place.get("formattedAddress", "")

        print(f"  Found place ID: {place_id}")
        print(f"  → {rating} ⭐ ({review_count} reviews)")

        data["locations"][place_id] = {
            "name": name,
            "address": address,
            "rating": rating,
            "review_count": review_count,
            "last_updated": today,
        }

        if place_id not in data["history"]:
