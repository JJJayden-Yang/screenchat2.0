import os
import tempfile
import unittest

from screenchat.memory import database


class DatabaseCoachingEventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tmp.name, "history.db")
        database.init()

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_insert_coaching_event_is_returned_in_today_history(self):
        database.insert_coaching_event(
            "reminder",
            "这个视频页和目标不相关，要不要切回编辑器？",
            screen_summary="视频页面",
            coaching_state="distracted",
            target_relevance="和目标不相关",
            suggested_action="切回编辑器",
            target_goal="写完 README",
            goal_type="学习/看文档",
            intensity="标准",
        )

        records = database.get_today()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].event_type, "reminder")
        self.assertEqual(records[0].coaching_state, "distracted")
        self.assertEqual(records[0].target_goal, "写完 README")
        self.assertEqual(records[0].suggested_action, "切回编辑器")


if __name__ == "__main__":
    unittest.main()
