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
    print(f"  Search
