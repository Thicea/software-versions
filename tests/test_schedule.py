import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_refresh_due import research_due

ROOT = Path(__file__).resolve().parents[1]
JST = ZoneInfo('Asia/Tokyo')


class ScheduleRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'versions.json').read_text())
        self.data['checkedAt'] = '2026-11-09T22:04:13+09:00'

    def test_primary_and_recovery_triggers_require_research_when_yesterday_is_published(self):
        for hour, minute in [(8, 30), (8, 45), (9, 15)]:
            with self.subTest(hour=hour, minute=minute):
                self.assertTrue(research_due(self.data, datetime(2026, 11, 10, hour, minute, tzinfo=JST)))

    def test_successful_morning_run_skips_late_primary_and_recovery_runs(self):
        self.data['checkedAt'] = '2026-11-10T08:42:55+09:00'
        for hour, minute in [(8, 45), (9, 15), (10, 0)]:
            with self.subTest(hour=hour, minute=minute):
                self.assertFalse(research_due(self.data, datetime(2026, 11, 10, hour, minute, tzinfo=JST)))

    def test_before_morning_research_does_not_skip_scheduled_research(self):
        self.data['checkedAt'] = '2026-11-10T02:30:00+09:00'
        self.assertTrue(research_due(self.data, datetime(2026, 11, 10, 8, 30, tzinfo=JST)))

    def test_null_timestamp_requires_research(self):
        self.data['checkedAt'] = None
        self.assertTrue(research_due(self.data, datetime(2026, 11, 10, 8, 30, tzinfo=JST)))

    def test_utc_timestamp_and_trigger_are_compared_in_japan_time(self):
        self.data['checkedAt'] = '2026-11-09T23:42:55Z'
        self.assertFalse(research_due(self.data, datetime(2026, 11, 10, 0, 15, tzinfo=timezone.utc)))

    def test_weekends_and_early_arrivals_do_not_run_research(self):
        for now in [datetime(2026, 11, 14, 8, 45, tzinfo=JST), datetime(2026, 11, 15, 9, 15, tzinfo=JST),
                    datetime(2026, 11, 10, 8, 29, tzinfo=JST)]:
            with self.subTest(now=now):
                self.assertFalse(research_due(self.data, now))

    def test_future_research_timestamp_cannot_suppress_todays_run(self):
        self.data['checkedAt'] = '2026-11-11T08:30:00+09:00'
        with self.assertRaises(ValueError):
            research_due(self.data, datetime(2026, 11, 10, 8, 45, tzinfo=JST))

    def test_recovery_utc_weekdays_map_to_jst_weekdays(self):
        workflow = (ROOT / '.github/workflows/refresh-versions.yml').read_text()
        for expression, start, expected in [
            ('45 23 * * 0-4', datetime(2026, 11, 8, 23, 45, tzinfo=timezone.utc), (8, 45)),
            ('15 0 * * 1-5', datetime(2026, 11, 9, 0, 15, tzinfo=timezone.utc), (9, 15)),
        ]:
            self.assertIn("cron: '" + expression + "'", workflow)
            local = [(start + timedelta(days=i)).astimezone(JST) for i in range(5)]
            self.assertEqual([value.weekday() for value in local], [0, 1, 2, 3, 4])
            self.assertTrue(all((value.hour, value.minute) == expected for value in local))


if __name__ == '__main__':
    unittest.main()
