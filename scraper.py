import os
import json
import requests
from datetime import datetime, timezone, timedelta

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

LOCATIONS = [
    {
        "name": "Avis Car Rental - Harry Reid Airport",
        "place_id": "ChIJL7BqEp3FyIARP_QZDyQ5HJI"
    },
]

DATA_FILE = "data/ratings.json"
LAS_VEGAS_OFFSET = timedelta(hours=-7)

def get_lv_time():
    return datetime.now(timezone.utc) + LAS_VEGAS_OFFSET

def fetch_reviews(place_id, sort):
    """Fetch reviews for a place with a given sort order."""
    url = "https://places.googleapis.com/v1/places/" + place_id
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "id,displayName,rating,userRatingCount,formattedAddress,reviews",
        "X-Goog-LanguageCode": "en",
        "reviewsSort": sort,
    }
    response = requests.get(url, headers=headers)
    if not response.ok:
        print("Warning: " + sort + " fetch returned " + str(response.status_code) + " - " + response.text[:200])
        return None
    return response.json()

def fetch_place(place_id):
    """Fetch place with newest + relevant reviews merged."""
    newest_data = fetch_reviews(place_id, "newest")
    relevant_data = fetch_reviews(place_id, "mostRelevant")

    # Use whichever succeeded for place metadata
    base = newest_data or relevant_data
    if not base:
        raise ValueError("Both review fetches failed for place_id: " + place_id)

    reviews_newest = (newest_data or {}).get("reviews", [])
    reviews_relevant = (relevant_data or {}).get("reviews", [])

    print("Newest reviews fetched: " + str(len(reviews_newest)))
    print("Relevant reviews fetched: " + str(len(reviews_relevant)))

    # Merge, newest first, deduplicated
    seen = set()
    merged = []
    for r in reviews_newest + reviews_relevant:
        author = r.get("authorAttribution", {}).get("displayName", "")
        t = r.get("publishTime", "")
        key = author + "_" + t
        if key not in seen:
            seen.add(key)
            merged.append(r)

    base["reviews"] = merged
    print("Total unique reviews after merge: " + str(len(merged)))
    return base

def extract_employee_names(review_text):
    if not ANTHROPIC_KEY:
        return []
    if not review_text or len(review_text.strip()) < 5:
        return []
    try:
        prompt = (
            "Read this car rental review and extract any employee first names or nicknames mentioned. "
            "Return ONLY a JSON array of name strings, nothing else. "
            "If no employee names are mentioned, return an empty array []. "
            "Examples: [\"Mike\", \"Sandra\"] or [\"Big John\"] or []\n\n"
            "Review: " + review_text
        )
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        names = json.loads(text)
        if isinstance(names, list):
            return [str(n).strip() for n in names if n]
        return []
    except Exception as e:
        print("Name extraction error: " + str(e))
        return []

def load_existing_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "locations": {},
        "history": {},
        "reviews": {},
        "daily_baselines": {},
        "employee_mentions": {},
        "seen_review_ids": {}
    }

def save_data(data):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_work_day_key(lv_now):
    if lv_now.hour < 3:
        day = (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        day = lv_now.strftime("%Y-%m-%d")
    return day

def main():
    if not API_KEY:
        raise EnvironmentError("GOOGLE_PLACES_API_KEY secret is not set.")

    lv_now = get_lv_time()
    today_key = get_work_day_key(lv_now)
    today_date = lv_now.strftime("%Y-%m-%d")
    now_str = lv_now.strftime("%Y-%m-%d %H:%M")
    lv_hour = lv_now.hour

    data = load_existing_data()

    for key in ["reviews", "daily_baselines", "employee_mentions", "seen_review_ids"]:
        if key not in data:
            data[key] = {}

    for location in LOCATIONS:
        name = location["name"]
        place_id = location["place_id"]
        print("Fetching: " + name)

        place = fetch_place(place_id)
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        address = place.get("formattedAddress", "")
        raw_reviews = place.get("reviews", [])

        print("Rating: " + str(rating) + " (" + str(review_count) + " reviews)")

        # Daily baseline
        baseline_key = place_id + "_" + today_key
        if baseline_key not in data["daily_baselines"]:
            if lv_hour >= 8 or lv_hour < 3:
                data["daily_baselines"][baseline_key] = review_count
                print("Set daily baseline: " + str(review_count))

        baseline = data["daily_baselines"].get(baseline_key, review_count)
        reviews_today = max(0, review_count - baseline)
        print("Reviews gained today: " + str(reviews_today))

        data["locations"][place_id] = {
            "name": name,
            "address": address,
            "rating": rating,
            "review_count": review_count,
            "reviews_today": reviews_today,
            "last_updated": now_str,
            "today_key": today_key,
        }

        # History
        if place_id not in data["history"]:
            data["history"][place_id] = []
        existing_dates = [h["date"] for h in data["history"][place_id]]
        if today_date not in existing_dates:
            data["history"][place_id].append({
                "date": today_date,
                "rating": rating,
                "review_count": review_count,
            })
        else:
            for h in data["history"][place_id]:
                if h["date"] == today_date:
                    h["rating"] = rating
                    h["review_count"] = review_count

        if place_id not in data["reviews"]:
            data["reviews"][place_id] = []
        if place_id not in data["employee_mentions"]:
            data["employee_mentions"][place_id] = {}
        if place_id not in data["seen_review_ids"]:
            data["seen_review_ids"][place_id] = []

        # seen_review_ids = every review we have EVER processed
        # ensures employee mentions are never double counted
        seen_ids = set(data["seen_review_ids"][place_id])
        fresh_reviews = []

        for review in raw_reviews:
            author = review.get("authorAttribution", {}).get("displayName", "Anonymous")
            publish_time = review.get("publishTime", "")
            review_id = author + "_" + publish_time
            text_field = review.get("text", "")
            if isinstance(text_field, dict):
                text = text_field.get("text", "")
            else:
                text = str(text_field)
            star_rating = review.get("rating", 0)

            if review_id in seen_ids:
                # Already counted — reuse stored names for display
                existing = next((r for r in data["reviews"][place_id] if r.get("id") == review_id), None)
                names = existing.get("employee_names", []) if existing else []
                print("Already seen: " + author)
            else:
                # New review — extract names and add to shoutouts
                print("New review from: " + author)
                names = extract_employee_names(text)
                if names:
                    print("Employees mentioned: " + str(names))
                    for emp_name in names:
                        emp_key = emp_name.lower()
                        if emp_key not in data["employee_mentions"][place_id]:
                            data["employee_mentions"][place_id][emp_key] = {
                                "display_name": emp_name,
                                "count": 0,
                                "last_mentioned": ""
                            }
                        data["employee_mentions"][place_id][emp_key]["count"] += 1
                        data["employee_mentions"][place_id][emp_key]["last_mentioned"] = today_date
                seen_ids.add(review_id)

            fresh_reviews.append({
                "id": review_id,
                "author": author,
                "rating": star_rating,
                "text": text,
                "date": today_date,
                "employee_names": names if names else [],
            })

        # Persist seen IDs and put freshest reviews first
        data["seen_review_ids"][place_id] = list(seen_ids)
        fresh_ids = {r["id"] for r in fresh_reviews}
        older = [r for r in data["reviews"][place_id] if r["id"] not in fresh_ids]
        data["reviews"][place_id] = fresh_reviews + older
        data["reviews"][place_id] = data["reviews"][place_id][:100]

    save_data(data)
    print("Data saved to " + DATA_FILE)

if __name__ == "__main__":
    main()
