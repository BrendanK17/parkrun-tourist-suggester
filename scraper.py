# filename: scraper.py

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

BASE_URL = "https://www.parkrun.org.uk"


def get_all_events():
    url = f"{BASE_URL}/events/events/"
    print(f"Fetching list of parkrun events...")
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')

    table = soup.find('table', {'id': 'events'})
    rows = table.find_all('tr')[1:]

    events = []
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 5:
            continue

        name = cols[0].text.strip()
        location = cols[1].text.strip()
        event_url = cols[0].find('a')['href']

        if "London" not in location:
            continue  # Skip non-London events for now

        events.append({
            'name': name,
            'location': location,
            'url': event_url
        })

    print(f"Found {len(events)} London-based parkruns.")
    return events


def get_event_history(event_url):
    history_url = f"{event_url}results/eventhistory/"
    time.sleep(1)  # Be polite
    print(f"Scraping: {history_url}")
    try:
        res = requests.get(history_url)
        soup = BeautifulSoup(res.text, 'html.parser')
        tables = pd.read_html(res.text)
        if not tables:
            return None
        df = tables[0]
        return len(df)  # Number of events held
    except Exception as e:
        print(f"Error reading {history_url}: {e}")
        return None


def main():
    events = get_all_events()
    results = []

    for event in events:
        num_events = get_event_history(event['url'])
        if num_events is None:
            continue

        upcoming = num_events + 1
        if upcoming % 50 == 0:  # Milestone: 50, 100, 250, 500
            results.append({
                'name': event['name'],
                'location': event['location'],
                'event_number': upcoming,
                'url': event['url']
            })

    print("\nUpcoming milestone events in London:")
    for r in results:
        print(f"{r['name']} – Event #{r['event_number']} – {r['url']}")

    # Optionally export to CSV
    df = pd.DataFrame(results)
    df.to_csv('milestone_parkruns_london.csv', index=False)


if __name__ == "__main__":
    main()
