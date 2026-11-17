import unittest
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from publication_schedule import wait_for_stage, verify_today

JST = ZoneInfo('Asia/Tokyo')


class Clock:
    def __init__(self, now):
        self.now = now
        self.waits = []

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += timedelta(seconds=seconds)


class PublicationScheduleTests(unittest.TestCase):
    def test_early_runner_waits_but_research_is_not_from_the_night(self):
        clock = Clock(datetime(2026, 11, 18, 2, 35, tzinfo=JST))
        self.assertTrue(wait_for_stage('research', 'schedule', lambda: clock.now, clock.sleep))
        self.assertEqual((clock.now.hour, clock.now.minute), (8, 30))
        self.assertLess(sum(clock.waits), 360 * 60)
        self.assertLessEqual(max(clock.waits), 60)

    def test_publication_waits_until_0838_and_late_runs_do_not_wait(self):
        clock = Clock(datetime(2026, 11, 18, 8, 31, tzinfo=JST))
        wait_for_stage('publish', 'schedule', lambda: clock.now, clock.sleep)
        self.assertEqual((clock.now.hour, clock.now.minute), (8, 38))
        clock = Clock(datetime(2026, 11, 18, 9, 0, tzinfo=JST))
        wait_for_stage('publish', 'schedule', lambda: clock.now, clock.sleep)
        self.assertEqual(clock.waits, [])

    def test_manual_and_config_checks_run_immediately(self):
        for event in ('push', 'workflow_dispatch'):
            clock = Clock(datetime(2026, 11, 18, 2, 35, tzinfo=JST))
            self.assertTrue(wait_for_stage('research', event, lambda: clock.now, clock.sleep))
            self.assertEqual(clock.waits, [])

    def test_previous_day_and_pre_morning_data_cannot_be_published(self):
        now = datetime(2026, 11, 18, 8, 38, tzinfo=JST)
        for timestamp in ['2026-11-17T08:31:00+09:00', '2026-11-18T02:35:00+09:00', '2026-11-18T09:00:00+09:00']:
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                verify_today({'checkedAt': timestamp}, now, scheduled=True)
        verify_today({'checkedAt': '2026-11-17T23:31:00Z'}, now, scheduled=True)

    def test_weekend_preparation_does_not_start_research(self):
        clock = Clock(datetime(2026, 11, 21, 3, 0, tzinfo=JST))
        self.assertFalse(wait_for_stage('research', 'schedule', lambda: clock.now, clock.sleep))
        self.assertEqual(clock.waits, [])

    def test_wait_cannot_silently_cross_into_another_japan_day(self):
        clock = Clock(datetime(2026, 11, 18, 8, 29, tzinfo=JST))
        def stalled_runner(seconds):
            clock.now += timedelta(days=1)
        with self.assertRaises(ValueError):
            wait_for_stage('research', 'schedule', lambda: clock.now, stalled_runner)


if __name__ == '__main__':
    unittest.main()
