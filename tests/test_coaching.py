import json
import unittest
from datetime import datetime, timedelta, timezone

from screenchat.coaching import (
    CoachingIntensity,
    CoachingSession,
    CoachingState,
    parse_analysis,
    should_interrupt,
    valid_action_message,
)


class CoachingStateTests(unittest.TestCase):
    def test_standard_intensity_allows_distracted_after_six_minutes(self):
        session = CoachingSession(
            goal="写完 README",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        )
        session.last_state = CoachingState.DISTRACTED
        session.state_started_at = session.started_at

        decision = should_interrupt(
            session,
            state=CoachingState.DISTRACTED,
            confidence=0.85,
            now=session.started_at + timedelta(minutes=6),
            ai_should_interrupt=True,
            message="这个视频页和『写完 README』不太相关，已经停了 6 分钟。要不要先切回编辑器？",
        )

        self.assertTrue(decision.allowed)

    def test_first_distracted_interrupt_is_allowed_immediately(self):
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=15,
            intensity=CoachingIntensity.STANDARD,
            started_at=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        )
        session.last_state = CoachingState.DISTRACTED
        session.state_started_at = session.started_at + timedelta(minutes=1)

        decision = should_interrupt(
            session,
            state=CoachingState.DISTRACTED,
            confidence=0.9,
            now=session.started_at + timedelta(minutes=1),
            ai_should_interrupt=True,
            message="这个页面和『看学习视频』不太相关。要不要先切回学习视频？",
        )

        self.assertTrue(decision.allowed)

    def test_reminder_limit_blocks_after_standard_limit(self):
        session = CoachingSession(
            goal="修完启动报错",
            goal_type="写代码/修 bug",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        )
        session.reminder_count = 4
        session.last_state = CoachingState.STUCK
        session.state_started_at = session.started_at

        decision = should_interrupt(
            session,
            state=CoachingState.STUCK,
            confidence=0.9,
            now=session.started_at + timedelta(minutes=20),
            ai_should_interrupt=True,
            message="这个报错页停了 10 分钟，和目标相关但像是卡住了。要不要我帮你看错误栈？",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "提醒次数已达上限")

    def test_low_confidence_is_unclear_and_silent(self):
        session = CoachingSession(
            goal="不要刷视频",
            goal_type="防走神",
            duration_minutes=25,
            intensity=CoachingIntensity.STRICT,
            started_at=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        )

        decision = should_interrupt(
            session,
            state=CoachingState.DISTRACTED,
            confidence=0.4,
            now=session.started_at + timedelta(minutes=20),
            ai_should_interrupt=True,
            message="视频页和目标不相关，要不要切回去？",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.state, CoachingState.UNCLEAR)

    def test_parse_analysis_accepts_markdown_json_and_normalizes_state(self):
        raw = """```json
        {"state": "stuck", "confidence": 0.92, "screen_summary": "终端报错",
         "target_relevance": "和修启动报错相关", "should_interrupt": true,
         "message": "这个报错页停了挺久，和『修启动报错』相关。要不要我帮你看错误栈？",
         "suggested_action": "复制报错给我看"}
        ```"""

        analysis = parse_analysis(raw)

        self.assertEqual(analysis.state, CoachingState.STUCK)
        self.assertEqual(analysis.confidence, 0.92)
        self.assertTrue(analysis.should_interrupt)
        self.assertEqual(analysis.suggested_action, "复制报错给我看")

    def test_parse_analysis_invalid_json_defaults_to_unclear(self):
        analysis = parse_analysis("这个页面有点抽象")

        self.assertEqual(analysis.state, CoachingState.UNCLEAR)
        self.assertFalse(analysis.should_interrupt)
        self.assertEqual(analysis.message, "")

    def test_valid_action_message_rejects_pure_cheering(self):
        self.assertFalse(valid_action_message("加油加油"))
        self.assertFalse(valid_action_message("哈哈这个有点抽象"))
        self.assertTrue(
            valid_action_message(
                "这个视频页和『写完 README』不太相关，已经停了 6 分钟。要不要先切回编辑器？"
            )
        )


if __name__ == "__main__":
    unittest.main()
