import unittest
from datetime import datetime, timedelta, timezone

from screenchat.tray.icon import pause_menu_title


class TrayMenuTests(unittest.TestCase):
    def test_pause_menu_title_shows_resume_arrow_and_remaining_pause_time(self):
        now = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)
        status = {
            "paused": True,
            "paused_until": (now + timedelta(seconds=75)).isoformat(),
            "pause_count": 1,
        }

        title = pause_menu_title(status, now)

        self.assertEqual(title, "▶ 继续专注（01:15）")

    def test_pause_menu_title_shows_pause_icon_when_running(self):
        title = pause_menu_title({"paused": False, "pause_count": 1})

        self.assertEqual(title, "Ⅱ 暂停专注")


if __name__ == "__main__":
    unittest.main()
