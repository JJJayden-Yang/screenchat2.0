import unittest
from datetime import datetime, timedelta, timezone

from screenchat.coaching import CoachingIntensity, CoachingSession
from screenchat.loop import bounded_sleep_interval


class LoopTimingTests(unittest.TestCase):
    def test_bounded_sleep_interval_does_not_sleep_past_focus_end(self):
        now = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=1,
            intensity=CoachingIntensity.STANDARD,
            started_at=now - timedelta(seconds=50),
        )
        session.check_interval_seconds = 900

        self.assertEqual(bounded_sleep_interval(session, session.check_interval_seconds, now), 10)


if __name__ == "__main__":
    unittest.main()
