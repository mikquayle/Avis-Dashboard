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

def fetch_place(place_id):
    url = "https://places.googleapis.com/v1/places/" + place_id
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "id,displayName,rating,userRatingCount,formattedAddress,reviews",
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    data = response.json()
    print("Reviews fetched: " + str(len(data.get("reviews", []))))
    return data

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
            timeout=15,
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
        "counted_review_ids": {},
        "daily_stars": {},
        "weekly_stars": {}
    }

def save_data(data):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_week_key(dt):
    return dt.strftime("%Y-W%W")

def get_work_day_key(lv_now):
    if lv_now.hour < 6:
        return (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    return lv_now.strftime("%Y-%m-%d")

def award_daily_star(data, place_id, lv_now):
    if lv_now.hour != 0:
        return
    yesterday = (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    award_key = place_id + "_star_" + yesterday
    if data.get("daily_stars", {}).get(award_key):
        return
    employees = data.get("employee_mentions", {}).get(place_id, {})
    if not employees:
        return
    top = max(employees.items(), key=lambda x: x[1].get("count", 0), default=None)
    if not top or top[1].get("count", 0) == 0:
        return
    top_key = top[0]
    week_key = get_week_key(lv_now - timedelta(days=1))
    if "weekly_stars" not in data:
        data["weekly_stars"] = {}
    if place_id not in data["weekly_stars"]:
        data["weekly_stars"][place_id] = {}
    if week_key not in data["weekly_stars"][place_id]:
        data["weekly_stars"][place_id][week_key] = {}
    week_data = data["weekly_stars"][place_id][week_key]
    if sum(week_data.values()) >= 7:
        data["daily_stars"][award_key] = "max_week"
        return
    if week_data.get(top_key, 0) >= 3:
        data["daily_stars"][award_key] = "max_emp"
        return
    week_data[top_key] = week_data.get(top_key, 0) + 1
    data["daily_stars"][award_key] = top_key
    print("Star awarded to: " + top[1]["display_name"])

def reset_daily_counts(data, place_id, lv_now):
    if lv_now.hour != 0:
        return
    yesterday = (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    reset_key = place_id + "_reset_" + yesterday
    if data.get("daily_stars", {}).get(reset_key):
        return
    print("Midnight reset — clearing daily counts")
    for emp in data.get("employee_mentions", {}).get(place_id, {}).values():
        emp["count"] = 0
    # Also clear counted_review_ids so tomorrow's reviews get freshly processed
    data["counted_review_ids"][place_id] = []
    data["daily_stars"][reset_key] = "done"

def main():
    if not API_KEY:
        raise EnvironmentError("GOOGLE_PLACES_API_KEY secret is not set.")

    lv_now = get_lv_time()
    today_key = get_work_day_key(lv_now)
    today_date = lv_now.strftime("%Y-%m-%d")
    now_str = lv_now.strftime("%Y-%m-%d %H:%M")
    lv_hour = lv_now.hour

    data = load_existing_data()
    for k in ["reviews", "daily_baselines", "employee_mentions", "counted_review_ids", "daily_stars", "weekly_stars"]:
        if k not in data:
            data[k] = {}

    for location in LOCATIONS:
        name = location["name"]
        place_id = location["place_id"]
        print("Fetching: " + name)

        # Midnight: award star then reset before fetching
        award_daily_star(data, place_id, lv_now)
        reset_daily_counts(data, place_id, lv_now)

        place = fetch_place(place_id)
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        address = place.get("formattedAddress", "")
        raw_reviews = place.get("reviews", [])

        print("Rating: " + str(rating) + " (" + str(review_count) + ")")

        # Baselines
        baseline_key = place_id + "_" + today_key
        if baseline_key not in data["daily_baselines"] and lv_hour >= 6:
            data["daily_baselines"][baseline_key] = review_count
            print("Set daily baseline: " + str(review_count))

        morning_key = place_id + "_morning_" + today_key
        if morning_key not in data["daily_baselines"] and lv_hour >= 6:
            data["daily_baselines"][morning_key] = review_count

        night_key = place_id + "_night_" + today_key
        if night_key not in data["daily_baselines"] and lv_hour >= 16:
            data["daily_baselines"][night_key] = review_count
            print("Set night baseline: " + str(review_count))

        baseline = data["daily_baselines"].get(baseline_key, review_count)
        morning_baseline = data["daily_baselines"].get(morning_key, review_count)
        night_baseline = data["daily_baselines"].get(night_key)

        reviews_today = max(0, review_count - baseline)

        if night_baseline is not None:
            reviews_morning = max(0, night_baseline - morning_baseline)
            reviews_night = max(0, review_count - night_baseline)
        else:
            reviews_morning = max(0, review_count - morning_baseline)
            reviews_night = 0

        print("Morning: " + str(reviews_morning) + " Night: " + str(reviews_night) + " Today: " + str(reviews_today))

        data["locations"][place_id] = {
            "name": name, "address": address, "rating": rating,
            "review_count": review_count, "reviews_today": reviews_today,
            "reviews_morning": reviews_morning, "reviews_night": reviews_night,
            "last_updated": now_str, "today_key": today_key,
        }

        # History
        if place_id not in data["history"]:
            data["history"][place_id] = []
        existing_dates = [h["date"] for h in data["history"][place_id]]
        if today_date not in existing_dates:
            data["history"][place_id].append({"date": today_date, "rating": rating, "review_count": review_count})
        else:
            for h in data["history"][place_id]:
                if h["date"] == today_date:
                    h["rating"] = rating
                    h["review_count"] = review_count

        if place_id not in data["reviews"]:
            data["reviews"][place_id] = []
        if place_id not in data["employee_mentions"]:
            data["employee_mentions"][place_id] = {}
        if place_id not in data["counted_review_ids"]:
            data["counted_review_ids"][place_id] = []

        # KEY FIX:
        # counted_review_ids = set of review IDs we have already counted toward shoutouts
        # We ALWAYS update the displayed reviews list with whatever Google returns
        # We ONLY skip shoutout counting for reviews already in counted_review_ids
        counted_ids = set(data["counted_review_ids"][place_id])

        # Build lookup of existing stored reviews so we can reuse employee_names for display
        stored_by_id = {r["id"]: r for r in data["reviews"][place_id]}

        fresh_reviews = []
        for review in raw_reviews:
            author = review.get("authorAttribution", {}).get("displayName", "Anonymous")
            publish_time = review.get("publishTime", "")
            review_id = author + "_" + publish_time
            text_field = review.get("text", "")
            text = text_field.get("text", "") if isinstance(text_field, dict) else str(text_field)
            star_rating = review.get("rating", 0)

            if review_id in counted_ids:
                # Already counted — reuse stored names, do NOT re-count
                names = stored_by_id.get(review_id, {}).get("employee_names", [])
                print("Already counted: " + author)
            else:
                # Never seen before — extract names and count toward shoutouts
                print("NEW: " + author + " " + str(star_rating) + "★ (" + publish_time[:10] + ")")
                names = extract_employee_names(text)
                if names:
                    print("  Employees: " + str(names))
                    for emp_name in names:
                        emp_key = emp_name.lower()
                        if emp_key not in data["employee_mentions"][place_id]:
                            data["employee_mentions"][place_id][emp_key] = {
                                "display_name": emp_name, "count": 0, "last_mentioned": ""
                            }
                        data["employee_mentions"][place_id][emp_key]["count"] += 1
                        data["employee_mentions"][place_id][emp_key]["last_mentioned"] = today_date
                counted_ids.add(review_id)

            fresh_reviews.append({
                "id": review_id, "author": author, "rating": star_rating,
                "text": text, "publish_time": publish_time,
                "date": today_date, "employee_names": names if names else [],
            })

        # Sort fresh reviews newest first
        fresh_reviews.sort(key=lambda r: r.get("publish_time", ""), reverse=True)

        # ALWAYS replace the top of the list with the freshest Google gave us
        # Keep older stored reviews below (ones Google no longer returns)
        fresh_ids = {r["id"] for r in fresh_reviews}
        older = [r for r in data["reviews"][place_id] if r["id"] not in fresh_ids]
        data["reviews"][place_id] = fresh_reviews + older
        data["reviews"][place_id] = data["reviews"][place_id][:100]
        data["counted_review_ids"][place_id] = list(counted_ids)

        print("Total reviews stored: " + str(len(data["reviews"][place_id])))
        print("Total counted IDs: " + str(len(counted_ids)))

    save_data(data)
    print("Saved.")

if __name__ == "__main__":
    main()
