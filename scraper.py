import os
import json
import requests
from datetime import datetime, timezone, timedelta
from openpyxl import Workbook, load_workbook

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

LOCATIONS = [
    {
        "name": "Avis Car Rental - Harry Reid Airport",
        "place_id": "ChIJL7BqEp3FyIARP_QZDyQ5HJI"
    },
]

DATA_FILE = "data/ratings.json"
MERGES_FILE = "data/merges.json"
LOG_FILE = "data/logs/Avis_Dashboard_Log.xlsx"
LAS_VEGAS_OFFSET = timedelta(hours=-7)

# ---------- time helpers ----------

def get_lv_time():
    return datetime.now(timezone.utc) + LAS_VEGAS_OFFSET

def get_work_day_key(lv_now):
    # Work day = 6:00 AM to 6:00 AM the next day
    if lv_now.hour < 6:
        return (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    return lv_now.strftime("%Y-%m-%d")

def get_work_day_key_from_iso(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        lv = dt.astimezone(timezone.utc) + LAS_VEGAS_OFFSET
    except Exception:
        lv = get_lv_time()
    return get_work_day_key(lv)

def get_week_key(dt):
    return dt.strftime("%Y-W%W")

# ---------- Google Places ----------

def fetch_place(place_id):
    url = "https://places.googleapis.com/v1/places/" + place_id
    headers = {
        "X-Goog-Api-Key": API_KEY,
        # IMPORTANT: list review sub-fields explicitly. Requesting the bare
        # "reviews" field can return incomplete/empty review objects.
        "X-Goog-FieldMask": "id,displayName,rating,userRatingCount,formattedAddress,"
                             "reviews.text,reviews.rating,reviews.publishTime,reviews.authorAttribution",
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

# ---------- persistence ----------

def load_existing_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_merges():
    if os.path.exists(MERGES_FILE):
        with open(MERGES_FILE, "r") as f:
            return json.load(f)
    return {}

def canonicalize(name, merges):
    key = name.lower().strip()
    canon_key = merges.get(key, key)
    display = merges.get("__display__" + canon_key, name.strip())
    return canon_key, display

# ---------- Excel logging ----------

def init_workbook():
    wb = Workbook()
    ws = wb.active
    ws.title = "Settings"
    ws["A1"] = "Avis Dashboard — Config"
    ws["A3"] = "Daily Review Goal"
    ws["B3"] = 50
    ws["A4"] = "Gift Card Shoutout Threshold (mentions/day)"
    ws["B4"] = 3
    ws["A5"] = "Work Day Window"
    ws["B5"] = "6:00 AM – 6:00 AM (next day)"
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 20

    ds = wb.create_sheet("Daily Summary")
    ds.append(["Date", "Rating (End of Day)", "Total Reviews (End of Day)",
               "True New Reviews Today", "Reviews w/ Text Captured", "Capture Rate", "Daily Goal Met?"])

    sd = wb.create_sheet("Shoutouts Daily")
    sd.append(["Date", "Week", "Employee (merged name)", "Mentions Today", "Threshold", "Gift Card Earned?"])

    sw = wb.create_sheet("Shoutouts Weekly")
    sw.append(["Week", "Employee (merged name)", "Total Mentions", "Threshold", "Gift Cards Earned (days met)"])
    return wb

def log_day_close(closed_date, week_key, rating, review_count_end, true_new, captured_count, employee_day_counts):
    os.makedirs("data/logs", exist_ok=True)
    wb = load_workbook(LOG_FILE) if os.path.exists(LOG_FILE) else init_workbook()

    ds = wb["Daily Summary"]
    r = ds.max_row + 1
    ds.cell(r, 1, closed_date)
    ds.cell(r, 2, rating)
    ds.cell(r, 3, review_count_end)
    ds.cell(r, 4, true_new)
    ds.cell(r, 5, captured_count)
    ds.cell(r, 6, "=IFERROR(E{0}/D{0},0)".format(r)).number_format = "0%"
    ds.cell(r, 7, '=IF(D{0}>=Settings!$B$3,"YES","NO")'.format(r))

    sd = wb["Shoutouts Daily"]
    for emp_key, info in employee_day_counts.items():
        r2 = sd.max_row + 1
        sd.cell(r2, 1, closed_date)
        sd.cell(r2, 2, week_key)
        sd.cell(r2, 3, info["display_name"])
        sd.cell(r2, 4, info["count"])
        sd.cell(r2, 5, "=Settings!$B$4")
        sd.cell(r2, 6, '=IF(D{0}>=E{0},"YES","NO")'.format(r2))

    sw = wb["Shoutouts Weekly"]
    existing = {(sw.cell(row=r, column=1).value, sw.cell(row=r, column=2).value)
                for r in range(2, sw.max_row + 1)}
    for emp_key, info in employee_day_counts.items():
        key = (week_key, info["display_name"])
        if key not in existing:
            r3 = sw.max_row + 1
            sw.cell(r3, 1, week_key)
            sw.cell(r3, 2, info["display_name"])
            sw.cell(r3, 3, "=SUMIFS('Shoutouts Daily'!D:D,'Shoutouts Daily'!B:B,A{0},'Shoutouts Daily'!C:C,B{0})".format(r3))
            sw.cell(r3, 4, "=Settings!$B$4")
            sw.cell(r3, 5, '=COUNTIFS(\'Shoutouts Daily\'!B:B,A{0},\'Shoutouts Daily\'!C:C,B{0},\'Shoutouts Daily\'!D:D,">="&D{0})'.format(r3))
            existing.add(key)

    wb.save(LOG_FILE)
    print("Excel log updated for " + closed_date)

# ---------- daily star (existing weekly star feature, now on 6am cutover) ----------

def award_daily_star(data, place_id, closed_date, week_key):
    award_key = place_id + "_star_" + closed_date
    if data.get("daily_stars", {}).get(award_key):
        return
    employees = data.get("employee_mentions", {}).get(place_id, {})
    if not employees:
        return
    top = max(employees.items(), key=lambda x: x[1].get("count", 0), default=None)
    if not top or top[1].get("count", 0) == 0:
        return
    top_key = top[0]
    data.setdefault("weekly_stars", {}).setdefault(place_id, {}).setdefault(week_key, {})
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

# ---------- cutover (close out the workday that just ended) ----------

def do_cutover(data, place_id, lv_now, review_count_now, rating_now):
    if lv_now.hour != 6:
        return
    closed_date = (lv_now - timedelta(days=1)).strftime("%Y-%m-%d")
    cutover_key = place_id + "_cutover_" + closed_date
    data.setdefault("cutover_done", {})
    if data["cutover_done"].get(cutover_key):
        return

    closed_baseline_key = place_id + "_" + closed_date
    closed_baseline = data.get("daily_baselines", {}).get(closed_baseline_key, review_count_now)
    true_new = max(0, review_count_now - closed_baseline)

    captured_count = data.get("captured_counts", {}).get(place_id, {}).get(closed_date, 0)

    employees = data.get("employee_mentions", {}).get(place_id, {})
    employee_day_counts = {k: {"display_name": v["display_name"], "count": v["count"]}
                            for k, v in employees.items() if v.get("count", 0) > 0}

    week_key = get_week_key(lv_now - timedelta(days=1))

    award_daily_star(data, place_id, closed_date, week_key)
    log_day_close(closed_date, week_key, rating_now, review_count_now, true_new, captured_count, employee_day_counts)

    # Reset today's tallies for the new workday
    for emp in employees.values():
        emp["count"] = 0
    data.setdefault("captured_counts", {}).setdefault(place_id, {})[closed_date] = 0

    data["cutover_done"][cutover_key] = True
    print("Cutover complete for " + closed_date + " — true new reviews: " + str(true_new))

# ---------- main ----------

def main():
    if not API_KEY:
        raise EnvironmentError("GOOGLE_PLACES_API_KEY secret is not set.")

    lv_now = get_lv_time()
    today_key = get_work_day_key(lv_now)
    today_date = lv_now.strftime("%Y-%m-%d")
    now_str = lv_now.strftime("%Y-%m-%d %H:%M")
    lv_hour = lv_now.hour

    data = load_existing_data()
    for k in ["locations", "history", "reviews", "daily_baselines", "employee_mentions",
              "counted_review_ids", "daily_stars", "weekly_stars", "captured_counts", "cutover_done"]:
        if k not in data:
            data[k] = {}

    merges = load_merges()

    for location in LOCATIONS:
        name = location["name"]
        place_id = location["place_id"]
        print("Fetching: " + name)

        place = fetch_place(place_id)
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        address = place.get("formattedAddress", "")
        raw_reviews = place.get("reviews", [])

        print("Rating: " + str(rating) + " (" + str(review_count) + ")")

        do_cutover(data, place_id, lv_now, review_count, rating)

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

        data["reviews"].setdefault(place_id, [])
        data["employee_mentions"].setdefault(place_id, {})
        data["counted_review_ids"].setdefault(place_id, [])
        data["captured_counts"].setdefault(place_id, {})

        counted_ids = set(data["counted_review_ids"][place_id])
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
                names = stored_by_id.get(review_id, {}).get("employee_names", [])
                print("Already counted: " + author)
            else:
                print("NEW: " + author + " " + str(star_rating) + "★ (" + publish_time[:10] + ")")
                names = extract_employee_names(text)

                review_work_day = get_work_day_key_from_iso(publish_time) if publish_time else today_key
                data["captured_counts"][place_id][review_work_day] = \
                    data["captured_counts"][place_id].get(review_work_day, 0) + 1

                if names:
                    print("  Employees: " + str(names))
                    for emp_name in names:
                        emp_key, display_name = canonicalize(emp_name, merges)
                        if emp_key not in data["employee_mentions"][place_id]:
                            data["employee_mentions"][place_id][emp_key] = {
                                "display_name": display_name, "count": 0, "last_mentioned": ""
                            }
                        data["employee_mentions"][place_id][emp_key]["count"] += 1
                        data["employee_mentions"][place_id][emp_key]["last_mentioned"] = today_date
                counted_ids.add(review_id)

            fresh_reviews.append({
                "id": review_id, "author": author, "rating": star_rating,
                "text": text, "publish_time": publish_time,
                "date": today_date, "employee_names": names if names else [],
            })

        fresh_reviews.sort(key=lambda r: r.get("publish_time", ""), reverse=True)
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
