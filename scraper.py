import os
import re
import json
import time
import random
import requests
from datetime import datetime, timedelta
from pytz import timezone, utc
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# Constants
DEFAULT_PARKRUN_ID = ""
EVENTS_JSON_URL = "https://images.parkrun.com/events.json"
CACHE_FILE = "event_number_cache.json"
COMPLETED_CACHE_FILE = "completed_events_cache.json"
CANCELLATIONS_URL = "https://www.parkrun.com/cancellations/"
LANDMARKS = {1, 5, 10, 25, 50, 100, 200, 250, 300, 400, 500, 600, 700, 750, 800, 900, 1000}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

def get_user_inputs():
    postcode = input("Enter your postcode (e.g., E14 5AB): ").strip()
    radius_km = float(input("How far are you willing to travel? (km): ") or 10)
    parkrun_id = input("Enter your parkrun ID (numbers only, or blank to use default): ").strip() or DEFAULT_PARKRUN_ID
    filter_unvisited = input("Show only parkruns you haven't done yet? (y/n): ").strip().lower() == "y"
    return postcode, radius_km, parkrun_id, filter_unvisited

def geocode_postcode(postcode):
    loc = Nominatim(user_agent="parkrun-tourist-suggester").geocode(postcode, timeout=10)
    if not loc:
        raise ValueError("Could not geocode postcode.")
    print(f"Geocoded '{postcode}' → {loc.latitude}, {loc.longitude}")
    return loc.latitude, loc.longitude

def fetch_event_data():
    print("Fetching event data from JSON feed…")
    resp = requests.get(EVENTS_JSON_URL)
    resp.raise_for_status()
    return resp.json()["events"]["features"]

def load_completed_cache():
    if not os.path.exists(COMPLETED_CACHE_FILE):
        return {"last_updated": None, "completed": {}}
    with open(COMPLETED_CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_completed_cache(data):
    with open(COMPLETED_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def should_refresh_completed_cache(parkrun_id, cache):
    if parkrun_id not in cache["completed"]:
        return True
    last_updated_str = cache.get("last_updated")
    if not last_updated_str:
        return True

    # Refresh only on Sundays after midnight UK time
    uk = timezone("Europe/London")
    now_uk = datetime.now(uk)
    if now_uk.weekday() == 6:  # Sunday
        last_updated = datetime.fromisoformat(last_updated_str)
        if last_updated.tzinfo is None:
            last_updated = utc.localize(last_updated)
        return now_uk.astimezone(utc) > last_updated
    return False

def get_completed_events(parkrun_id, cache):
    if not should_refresh_completed_cache(parkrun_id, cache):
        return set(cache["completed"].get(parkrun_id, []))

    print(f"🔁 Refreshing completed events for parkrun ID {parkrun_id}")
    url = f"https://www.parkrun.org.uk/parkrunner/{parkrun_id}/"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        print(f"Error fetching profile page: HTTP {resp.status_code}")
        return set()

    soup = BeautifulSoup(resp.text, "html.parser")
    heading = soup.find(string=re.compile("Event Summaries", re.I))
    if not heading:
        print("Could not find 'Event Summaries'")
        return set()

    table = heading.find_next("table")
    if not table:
        print("No results table after heading")
        return set()

    completed = set()
    for row in table.find_all("tr")[1:]:
        a = row.find("td").find("a", href=True)
        if a:
            slug = a["href"].rstrip("/").split("/")[-2].lower()
            completed.add(slug)

    # Update cache
    cache["completed"][parkrun_id] = list(completed)
    uk = timezone("Europe/London")
    now_uk = datetime.now(uk).astimezone(utc)
    cache["last_updated"] = now_uk.isoformat()
    save_completed_cache(cache)

    return completed

def calculate_distance(coord1, coord2):
    return round(geodesic(coord1, coord2).km, 2)

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {"last_updated": None, "event_numbers": {}}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def should_refresh_cache(slugs, cache):
    if any(cache["event_numbers"].get(slug) is None for slug in slugs):
        return True

    # Refresh only on Sundays after midnight UK time
    uk = timezone("Europe/London")
    now_uk = datetime.now(uk)
    if now_uk.weekday() == 6:  # Sunday
        last_updated_str = cache.get("last_updated")
        if not last_updated_str:
            return True
        last_updated = datetime.fromisoformat(last_updated_str)
        if last_updated.tzinfo is None:
            last_updated = utc.localize(last_updated)
        return now_uk.astimezone(utc) > last_updated
    return False

def fetch_event_number(slug):
    url = f"https://www.parkrun.org.uk/{slug}/results/latestresults/"
    print(f"[{slug}] 🔍 Fetching: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        match = re.search(r"Events:\s*([\d,]+)", text)
        if match:
            event_count_str = match.group(1)  # ← Now defined
            event_number = int(event_count_str.replace(',', ''))
            print(f"[{slug}] ✅ Total events: {event_number}")
            return event_number
        else:
            print(f"[{slug}] ❌ Could not find 'Events:' line.")

    except Exception as e:
        print(f"[{slug}] ❌ Exception: {e}")

    return None


def update_event_numbers_cache(slugs, cache):
    print(f"Fetching event numbers for {len(slugs)} parkruns...")
    for slug in slugs:
        if cache["event_numbers"].get(slug) is None:
            number = fetch_event_number(slug)
            cache["event_numbers"][slug] = number

            # Update last_updated timestamp on every save
            uk = timezone("Europe/London")
            now_uk = datetime.now(uk).astimezone(utc)
            cache["last_updated"] = now_uk.isoformat()

            save_cache(cache)  # Save after every update
            time.sleep(random.uniform(0.3, 1.3))  # slight random delay
    return cache["event_numbers"]


def fetch_saturday_cancellations():
    print("Fetching Saturday cancellations from parkrun.com...")
    resp = requests.get(CANCELLATIONS_URL, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the Saturday cancellations section by heading
    cancellations = {}
    saturday_heading = None

    # Find all h2 or h3 headings that mention Saturday
    for header in soup.find_all(['h2','h3']):
        if 'Saturday' in header.get_text():
            saturday_heading = header
            break

    if not saturday_heading:
        print("Could not find Saturday cancellations section.")
        return cancellations

    # Parse sibling elements until next h2/h3 or end of list
    sibling = saturday_heading.find_next_sibling()
    while sibling and sibling.name not in ['h2', 'h3']:
        # Extract lines that look like "Aberbeeg parkrun: Shortage of volunteers"
        if sibling.name == 'ul':
            for li in sibling.find_all('li'):
                text = li.get_text(strip=True)
                # Expect format: "<Event name> parkrun: Reason"
                # But on page, might be just text lines instead of list items, so handle both
                # We will parse "<Event name> parkrun: ..."
                # Some lines might be just text, so fallback
                match = re.match(r"(.+?) parkrun: (.+)", text)
                if match:
                    event_name = match.group(1).strip()
                    reason = match.group(2).strip()
                    # To get slug, we'll attempt a heuristic by matching event_name to slug later
                    cancellations[event_name.lower()] = reason
        elif sibling.name == 'p':
            # Sometimes cancellations might be in paragraphs, just skip
            pass
        sibling = sibling.find_next_sibling()

    # The above is a best-effort approach but the page format might differ slightly.
    # Alternative approach: parse text lines from Saturday section (some fallback)
    if not cancellations:
        # fallback: extract all lines under Saturday as plain text
        text_lines = []
        sib = saturday_heading.find_next_sibling()
        while sib and sib.name not in ['h2', 'h3']:
            text_lines.append(sib.get_text(separator="\n"))
            sib = sib.find_next_sibling()
        combined_text = "\n".join(text_lines)
        for line in combined_text.splitlines():
            line = line.strip()
            if line:
                match = re.match(r"(.+?) parkrun: (.+)", line)
                if match:
                    cancellations[match.group(1).lower()] = match.group(2)

    # At this point, cancellations keys are event names in lowercase, without slug info

    return cancellations

def filter_uk_cancellations(cancellations, features):
    # Build a set of UK slugs from features for quick lookup
    uk_slugs = set()
    slug_to_name = {}
    for feat in features:
        props = feat["properties"]
        slug = props.get("eventname")
        url = props.get("url") or f"https://www.parkrun.org.uk/{slug}/"
        if url.startswith("https://www.parkrun.org.uk/"):
            uk_slugs.add(slug.lower())
            slug_to_name[slug.lower()] = props.get("EventLongName", "")

    # Match cancellations by trying to find the slug from the name
    # Event name in cancellations is a plain name, sometimes slightly different, so we try fuzzy matching
    # To be robust, we'll match by lowercased name substrings

    # Create a map from lowercase event long name to slug for lookup
    name_to_slug = {v.lower(): k for k, v in slug_to_name.items()}

    # We'll attempt exact match on event name cancellation keys to event long name
    # If no exact match, try substring containment one way or the other

    filtered = {}
    for cancel_name, reason in cancellations.items():
        # Try exact match slug
        slug = None
        if cancel_name in name_to_slug:
            slug = name_to_slug[cancel_name]
        else:
            # Try substring match:
            for name_lower, slug_try in name_to_slug.items():
                if cancel_name in name_lower or name_lower in cancel_name:
                    slug = slug_try
                    break
        if slug and slug in uk_slugs:
            filtered[slug] = reason

    return filtered

def main():
    postcode, radius_km, parkrun_id, filter_unvisited = get_user_inputs()
    user_latlon = geocode_postcode(postcode)
    completed_cache = load_completed_cache()
    completed = get_completed_events(parkrun_id, completed_cache)
    features = fetch_event_data()

    # Fetch cancellations for the upcoming Saturday only
    cancellations_raw = fetch_saturday_cancellations()
    cancellations = filter_uk_cancellations(cancellations_raw, features)

    nearby = []

    for feat in features:
        props = feat["properties"]
        slug = props.get("eventname")
        if "junior" in slug:
            continue
        longname = props.get("EventLongName")
        lon, lat = feat["geometry"]["coordinates"]
        dist = calculate_distance(user_latlon, (lat, lon))
        if dist <= radius_km:
            done = slug in completed
            if not filter_unvisited or not done:
                nearby.append((dist, longname, slug, done))

    nearby.sort()
    slugs_to_check = [slug for _, _, slug, _ in nearby]
    cache = load_cache()

    if should_refresh_cache(slugs_to_check, cache):
        event_numbers = update_event_numbers_cache(slugs_to_check, cache)
    else:
        event_numbers = cache["event_numbers"]

    print(f"\nFound {len(nearby)} parkruns within {radius_km:.1f} km of {postcode.lower()}.\n")

    # Warn if it's Saturday UTC
    if datetime.utcnow().weekday() == 5:
        print("⚠️ Saturday UTC: parkrun results may not be available yet. Cache refresh happens Sunday 00:00 UK.")

    for dist, name, slug, done in nearby:
        num = event_numbers.get(slug)
        done_symbol = "✅" if done else ""
        cancel_reason = cancellations.get(slug)
        cancel_str = f"[CANCELLED: {cancel_reason}]" if cancel_reason else ""
        num_str = f", event #{num + 1 if num else '?'}" if num else ""
        # +1 because if 499 events completed, next event is 500th
        print(f"- {cancel_str} {name} ({slug}) at {dist:.2f} km{num_str} {done_symbol}")

if __name__ == "__main__":
    main()
