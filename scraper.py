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

def get_week_key(lv_now):
    return lv_now.strftime("%Y-W%W")

def get_work_day_key(lv_now):
    # Work day runs 6am - midnight
    if lv_now.hour < 6:
        day = (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        day = lv_now.strftime("%Y-%m-%d")
    return day

def award_daily_star(data, place_id, today_key, lv_now, lv_hour):
    """At midnight (hour 0-1), award a star to yesterday's #1 employee."""
    # Only run in the first 30 min after midnight
    if lv_hour != 0:
        return

    yesterday_key = (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    star_award_key = place_id + "_star_awarded_" + yesterday_key

    # Only award once per day
    if star_award_key in data.get("daily_stars", {}):
        print("Star already awarded for " + yesterday_key)
        return

    employees = data.get("employee_mentions", {}).get(place_id, {})
    if not employees:
        return

    # Find top employee by count
    top = max(employees.items(), key=lambda x: x[1].get("count", 0), default=None)
    if not top:
        return

    top_key, top_emp = top
    week_key = get_week_key(lv_now - timedelta(days=1))

    if "weekly_stars" not in data:
        data["weekly_stars"] = {}
    if place_id not in data["weekly_stars"]:
        data["weekly_stars"][place_id] = {}
    if week_key not in data["weekly_stars"][place_id]:
        data["weekly_stars"][place_id][week_key] = {}

    # Max 3 stars per employee, max 7 stars per week total
    week_data = data["weekly_stars"][place_id][week_key]
    total_stars_this_week = sum(week_data.values())

    if total_stars_this_week >= 7:
        print("Max 7 stars already awarded this week")
        data["daily_stars"][star_award_key] = "max_reached"
        return

    current_stars = week_data.get(top_key, 0)
    if current_stars >= 3:
        print(top_emp["display_name"] + " already has max 3 stars this week")
        data["daily_stars"][star_award_key] = "max_for_employee"
        return

    week_data[top_key] = current_stars + 1
    data["daily_stars"][star_award_key] = top_key
    print("⭐ Star awarded to " + top_emp["display_name"] + " for " + yesterday_key)

def reset_daily_counts(data, place_id, lv_now, lv_hour):
    """At midnight reset morning/night counts and employee mention counts."""
    if lv_hour != 0:
        return

    yesterday_key = (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    reset_key = place_id + "_reset_" + yesterday_key

    if reset_key in data.get("daily_stars", {}):
        print("Already reset for " + yesterday_key)
        return

    print("Midnight reset — clearing employee mention counts for new day")
    if place_id in data.get("employee_mentions", {}):
        for emp in data["employee_mentions"][place_id].values():
            emp["count"] = 0

    data["daily_stars"][reset_key] = "reset_done"

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
    for old_key in ["seen_review_ids", "processed_review_ids"]:
        if old_key in data:
            del data[old_key]

    for location in LOCATIONS:
        name = location["name"]
        place_id = location["place_id"]
        print("Fetching: " + name)

        # Award star and reset at midnight BEFORE fetching new data
        award_daily_star(data, place_id, today_key, lv_now, lv_hour)
        reset_daily_counts(data, place_id, lv_now, lv_hour)

        place = fetch_place(place_id)
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        address = place.get("formattedAddress", "")
        raw_reviews = place.get("reviews", [])

        print("Rating: " + str(rating) + " (" + str(review_count) + " reviews)")

        # Daily baseline — set once at 6am
        baseline_key = place_id + "_" + today_key
        if baseline_key not in data["daily_baselines"] and lv_hour >= 6:
            data["daily_baselines"][baseline_key] = review_count
            print("Set daily baseline: " + str(review_count))
        baseline = data["daily_baselines"].get(baseline_key, review_count)
        reviews_today = max(0, review_count - baseline)

        # Morning baseline set at 6am, never changes during the day
        morning_key = place_id + "_morning_" + today_key
        if morning_key not in data["daily_baselines"] and lv_hour >= 6:
            data["daily_baselines"][morning_key] = review_count
            print("Set morning baseline: " + str(review_count))

        # Night baseline set at 4pm
        night_key = place_id + "_night_" + today_key
        if night_key not in data["daily_baselines"] and lv_hour >= 16:
            data["daily_baselines"][night_key] = review_count
            print("Set night baseline: " + str(review_count))

        morning_baseline = data["daily_baselines"].get(morning_key, review_count)
        night_baseline = data["daily_baselines"].get(night_key, None)

        # Morning count: reviews since 6am baseline up to now (or up to night baseline if set)
        if night_baseline is not None:
            reviews_morning = max(0, night_baseline - morning_baseline)
            reviews_night = max(0, review_count - night_baseline)
        else:
            # Before 4pm — morning is accumulating, night not started
            reviews_morning = max(0, review_count - morning_baseline)
            reviews_night = 0

        print("Morning: " + str(reviews_morning) + " | Night: " + str(reviews_night) + " | Today: " + str(reviews_today))

        data["locations"][place_id] = {
            "name": name,
            "address": address,
            "rating": rating,
            "review_count": review_count,
            "reviews_today": reviews_today,
            "reviews_morning": reviews_morning,
            "reviews_night": reviews_night,
            "last_updated": now_str,
            "today_key": today_key,
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

        counted_ids = set(data["counted_review_ids"][place_id])
        stored_by_id = {r["id"]: r for r in data["reviews"][place_id]}
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

            if review_id in counted_ids:
                names = stored_by_id.get(review_id, {}).get("employee_names", [])
                print("Already counted: " + author)
            else:
                print("New review: " + author + " " + str(star_rating) + "★")
                names = extract_employee_names(text)
                if names:
                    print("  Employees: " + str(names))
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
                counted_ids.add(review_id)

            fresh_reviews.append({
                "id": review_id,
                "author": author,
                "rating": star_rating,
                "text": text,
                "publish_time": publish_time,
                "date": today_date,
                "employee_names": names if names else [],
            })

        fresh_reviews.sort(key=lambda r: r.get("publish_time", ""), reverse=True)
        fresh_ids = {r["id"] for r in fresh_reviews}
        older = [r for r in data["reviews"][place_id] if r["id"] not in fresh_ids]
        data["reviews"][place_id] = fresh_reviews + older
        data["reviews"][place_id] = data["reviews"][place_id][:100]
        data["counted_review_ids"][place_id] = list(counted_ids)

    save_data(data)
    print("Data saved to " + DATA_FILE)

if __name__ == "__main__":
    main()
