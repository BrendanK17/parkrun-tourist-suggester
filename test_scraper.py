import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from scraper import (
    should_refresh_completed_cache,
    should_refresh_cache,
    calculate_distance,
    geocode_postcode,
    fetch_saturday_cancellations,
    filter_uk_cancellations,
)
import pytz


class TestParkrunTouristSuggester(unittest.TestCase):

    def test_should_refresh_cache_missing_slug(self):
        cache = {"event_numbers": {"a": 100}, "last_updated": datetime.utcnow().isoformat()}
        self.assertTrue(should_refresh_cache(["a", "b"], cache))

    def test_should_refresh_cache_on_sunday(self):
        uk = pytz.timezone("Europe/London")
        sunday = datetime(2023, 1, 1, 10, 0, 0, tzinfo=uk)  # Sunday
        with patch("scraper.datetime") as mock_dt:
            mock_dt.now.return_value = sunday
            mock_dt.utcnow.return_value = sunday.astimezone(pytz.utc)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.weekday.return_value = 6
            cache = {"event_numbers": {"a": 100}, "last_updated": (sunday - timedelta(days=1)).isoformat()}
            self.assertTrue(should_refresh_cache(["a"], cache))

    def test_calculate_distance(self):
        london = (51.5074, -0.1278)
        oxford = (51.7520, -1.2577)
        dist = calculate_distance(london, oxford)
        self.assertAlmostEqual(dist, 83, delta=5)

    @patch("scraper.Nominatim.geocode")
    def test_geocode_postcode(self, mock_geocode):
        mock_geocode.return_value = MagicMock(latitude=51.5, longitude=0.1)
        result = geocode_postcode("E14 5AB")
        self.assertEqual(result, (51.5, 0.1))

    @patch("scraper.requests.get")
    def test_fetch_saturday_cancellations(self, mock_get):
        mock_html = """
        <html><body>
        <h3>Saturday 3rd Aug</h3>
        <ul>
        <li>Catford parkrun: Cancelled due to festival</li>
        <li>York parkrun: Horse racing</li>
        </ul>
        </body></html>
        """
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = mock_html

        cancellations = fetch_saturday_cancellations()
        self.assertIn("catford", cancellations)
        self.assertIn("york", cancellations)
        self.assertEqual(cancellations["catford"], "Cancelled due to festival")

    def test_filter_uk_cancellations(self):
        cancellations = {"catford": "muddy", "york": "race"}
        features = [
            {"properties": {"eventname": "catford", "EventLongName": "Catford parkrun", "url": "https://www.parkrun.org.uk/catford/"},
             "geometry": {"coordinates": [0, 0]}},
            {"properties": {"eventname": "edinburgh", "EventLongName": "Edinburgh parkrun", "url": "https://www.parkrun.org.uk/edinburgh/"},
             "geometry": {"coordinates": [0, 0]}}
        ]

        filtered = filter_uk_cancellations(cancellations, features)
        self.assertIn("catford", filtered)
        self.assertNotIn("york", filtered)

    def test_should_refresh_completed_cache_on_sunday(self):
        uk = pytz.timezone("Europe/London")
        sunday = datetime(2024, 2, 4, 12, 0, 0, tzinfo=uk)  # A Sunday
        with patch("scraper.datetime") as mock_dt:
            mock_dt.now.return_value = sunday
            mock_dt.utcnow.return_value = sunday.astimezone(pytz.utc)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.weekday.return_value = 6
            cache = {"completed": {"a": True}, "last_updated": (sunday - timedelta(days=1)).isoformat()}
            self.assertTrue(should_refresh_completed_cache("a", cache))
    def test_should_not_refresh_completed_cache_if_fresh(self):
        uk = pytz.timezone("Europe/London")
        sunday = datetime(2024, 2, 4, 12, 0, 0, tzinfo=uk)  # A Sunday
        with patch("scraper.datetime") as mock_dt:
            mock_dt.now.return_value = sunday
            mock_dt.utcnow.return_value = sunday.astimezone(pytz.utc)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.weekday.return_value = 6
            # Simulate a cache updated just now
            cache = {"completed": {"a": True}, "last_updated": sunday.isoformat()}
            self.assertFalse(should_refresh_completed_cache("a", cache))

if __name__ == "__main__":
    unittest.main()
