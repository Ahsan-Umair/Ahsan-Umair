import importlib.util
import unittest
from datetime import date, timedelta
from pathlib import Path

spec = importlib.util.spec_from_file_location("signal_card", Path(__file__).with_name("build_contribution_signal.py"))
card = importlib.util.module_from_spec(spec)
spec.loader.exec_module(card)

class ContributionSignalTests(unittest.TestCase):
    def days(self, start, counts):
        start = date.fromisoformat(start)
        return {(start + timedelta(days=i)).isoformat(): count for i, count in enumerate(counts)}

    def test_streak_crosses_year_boundary(self):
        stats = card.summarize(self.days("2025-12-30", [1, 4, 2]), date(2026, 1, 1))
        self.assertEqual(stats["current_streak"], 3)
        self.assertEqual(stats["longest_streak"], 3)
        self.assertEqual(stats["total_contributions"], 7)

    def test_today_can_still_be_in_progress(self):
        stats = card.summarize(self.days("2026-01-01", [2, 1, 0]), date(2026, 1, 3))
        self.assertEqual(stats["current_streak"], 2)
        self.assertEqual(stats["current_end"], "2026-01-02")

    def test_completed_empty_day_breaks_streak(self):
        stats = card.summarize(self.days("2026-01-01", [2, 3, 0, 0]), date(2026, 1, 4))
        self.assertEqual(stats["current_streak"], 0)
        self.assertEqual(stats["longest_streak"], 2)

    def test_private_count_fills_a_daily_gap(self):
        stats = card.summarize(self.days("2026-09-24", [10, 1, 9]), date(2026, 9, 26))
        self.assertEqual(stats["current_streak"], 3)
        self.assertEqual(stats["total_contributions"], 20)

    def test_parser_matches_tooltips_to_dates(self):
        source = '<td id="b" data-date="2026-01-02"></td><td id="a" data-date="2026-01-01"></td><tool-tip for="a">No contributions on January 1st.</tool-tip><tool-tip for="b">1,234 contributions on January 2nd.</tool-tip>'
        self.assertEqual(card.parse_calendar(source, 2026, date(2026, 1, 2)), {"2026-01-02": 1234, "2026-01-01": 0})

    def test_incomplete_calendar_is_rejected(self):
        with self.assertRaises(ValueError):
            card.parse_calendar('<td id="a" data-date="2026-01-01"></td><tool-tip for="a">1 contribution on January 1st.</tool-tip>', 2026, date(2026, 1, 2))

    def test_unrecognized_count_is_rejected(self):
        with self.assertRaises(ValueError):
            card.parse_calendar('<td id="a" data-date="2026-01-01"></td><tool-tip for="a">Unavailable</tool-tip>', 2026, date(2026, 1, 1))

if __name__ == "__main__":
    unittest.main()
