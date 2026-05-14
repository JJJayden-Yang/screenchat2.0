import json
import unittest
from datetime import datetime, timedelta, timezone

from screenchat.coaching import (
    CoachingIntensity,
    CoachingSession,
    CoachingState,
    build_focus_summary,
    fallback_intervention_message,
    idle_reminder_message,
    manual_end_notification,
    next_check_interval,
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

    def test_distracted_state_can_interrupt_even_when_ai_flag_is_false(self):
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
            ai_should_interrupt=False,
            message="这个页面和『看学习视频』不太相关。要不要先切回学习视频？",
        )

        self.assertTrue(decision.allowed)

    def test_reminder_limit_still_blocks_milestone_after_standard_limit(self):
        session = CoachingSession(
            goal="修完启动报错",
            goal_type="写代码/修 bug",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        )
        session.reminder_count = 4
        session.last_state = CoachingState.MILESTONE
        session.state_started_at = session.started_at

        decision = should_interrupt(
            session,
            state=CoachingState.MILESTONE,
            confidence=0.9,
            now=session.started_at + timedelta(minutes=20),
            ai_should_interrupt=True,
            message="这个目标已经完成了一个节点。下一步可以先运行测试，确认修复没有回退。",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "提醒次数已达上限")

    def test_repeated_distracted_reminders_are_not_blocked_by_old_session_limit(self):
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        )
        session.reminder_count = 9
        session.last_state = CoachingState.DISTRACTED
        session.state_started_at = session.started_at

        decision = should_interrupt(
            session,
            state=CoachingState.DISTRACTED,
            confidence=0.88,
            now=session.started_at + timedelta(minutes=12),
            ai_should_interrupt=True,
            message="这个页面和『看学习视频』不太相关。要不要先切回学习视频？",
        )

        self.assertTrue(decision.allowed)

    def test_fallback_intervention_message_turns_distracted_observation_into_action(self):
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        )

        message = fallback_intervention_message(
            session,
            CoachingState.DISTRACTED,
            screen_summary="浏览器打开了社交页面",
            target_relevance="和看学习视频不相关",
            suggested_action="切回课程页面",
        )

        self.assertIn("看学习视频", message)
        self.assertIn("不相关", message)
        self.assertIn("切回课程页面", message)

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

    def test_standard_check_interval_backs_off_until_fifteen_minutes(self):
        interval = 60
        for expected in (120, 240, 480, 900, 900):
            interval = next_check_interval(interval, CoachingState.ON_TRACK, CoachingIntensity.STANDARD)
            self.assertEqual(interval, expected)

    def test_light_check_interval_starts_slower_and_caps_at_fifteen_minutes(self):
        interval = 120
        for expected in (300, 600, 900, 900):
            interval = next_check_interval(interval, CoachingState.ON_TRACK, CoachingIntensity.LIGHT)
            self.assertEqual(interval, expected)

    def test_strict_check_interval_checks_more_often_and_caps_at_eight_minutes(self):
        interval = 60
        for expected in (120, 240, 480, 480):
            interval = next_check_interval(interval, CoachingState.ON_TRACK, CoachingIntensity.STRICT)
            self.assertEqual(interval, expected)

    def test_check_interval_resets_after_distracted_or_stuck(self):
        self.assertEqual(next_check_interval(900, CoachingState.DISTRACTED, CoachingIntensity.LIGHT), 120)
        self.assertEqual(next_check_interval(900, CoachingState.STUCK, CoachingIntensity.STANDARD), 60)
        self.assertEqual(next_check_interval(900, CoachingState.STUCK, CoachingIntensity.STRICT), 60)

    def test_unclear_keeps_current_interval(self):
        self.assertEqual(next_check_interval(240, CoachingState.UNCLEAR, CoachingIntensity.STANDARD), 240)

    def test_screen_still_tracks_idle_seconds_from_last_change(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )
        session.record_screen_change(started + timedelta(minutes=2))

        session.record_screen_still(started + timedelta(minutes=5))

        self.assertEqual(session.last_state, CoachingState.IDLE)
        self.assertEqual(session.still_seconds, 180)
        self.assertFalse(session.idle_reminder_due(started + timedelta(minutes=5)))

    def test_standard_idle_reminder_is_due_after_five_minutes_and_repeats_later(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )
        session.record_screen_still(started + timedelta(minutes=5))

        self.assertTrue(session.idle_reminder_due(started + timedelta(minutes=5)))
        session.record_idle_reminder(started + timedelta(minutes=5))
        self.assertFalse(session.idle_reminder_due(started + timedelta(minutes=6)))
        self.assertTrue(session.idle_reminder_due(started + timedelta(minutes=8)))

    def test_screen_change_clears_idle_tracking(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )
        session.record_screen_still(started + timedelta(minutes=6))

        session.record_screen_change(started + timedelta(minutes=7))

        self.assertEqual(session.still_seconds, 0)
        self.assertIsNone(session.still_started_at)
        self.assertEqual(session.last_screen_changed_at, started + timedelta(minutes=7))

    def test_multiple_idle_stretches_are_accumulated_for_session_summary(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )
        session.record_screen_still(started + timedelta(minutes=5))
        session.record_screen_change(started + timedelta(minutes=6))
        session.record_screen_still(started + timedelta(minutes=8))

        self.assertEqual(session.total_idle_seconds, 420)

    def test_idle_reminder_message_mentions_goal_and_idle_minutes(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )
        session.record_screen_still(started + timedelta(minutes=6))

        message = idle_reminder_message(session)

        self.assertIn("看学习视频", message)
        self.assertIn("6 分钟", message)
        self.assertIn("还在", message)

    def test_pause_extends_end_time_and_is_limited_to_two_minutes(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="写代码",
            goal_type="写代码/修 bug",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )

        self.assertTrue(session.pause(started + timedelta(minutes=10)))
        self.assertTrue(session.is_paused(started + timedelta(minutes=11)))
        self.assertFalse(session.is_paused(started + timedelta(minutes=13)))
        self.assertEqual(session.pause_count, 1)
        self.assertEqual(session.ends_at, started + timedelta(minutes=47))

    def test_pause_is_limited_to_two_times_per_session(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="写代码",
            goal_type="写代码/修 bug",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )

        self.assertTrue(session.pause(started + timedelta(minutes=1)))
        session.resume(started + timedelta(minutes=2))
        self.assertTrue(session.pause(started + timedelta(minutes=5)))
        session.resume(started + timedelta(minutes=6))
        self.assertFalse(session.pause(started + timedelta(minutes=9)))
        self.assertEqual(session.pause_count, 2)

    def test_manual_end_before_time_gets_encouraging_notification(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="写代码",
            goal_type="写代码/修 bug",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )

        message = manual_end_notification(session, started + timedelta(minutes=20))

        self.assertIn("先到这里", message)
        self.assertIn("写代码", message)

    def test_manual_end_after_time_uses_normal_notification(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="写代码",
            goal_type="写代码/修 bug",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )

        message = manual_end_notification(session, started + timedelta(minutes=46))

        self.assertEqual(message, "陪跑结束，已生成本轮总结。")

    def test_focus_summary_counts_time_pauses_and_early_end(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="写 todo 再写代码",
            goal_type="写代码/修 bug",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )
        self.assertTrue(session.pause(started + timedelta(minutes=10)))
        session.resume(started + timedelta(minutes=11, seconds=30))

        summary = build_focus_summary(
            session,
            now=started + timedelta(minutes=20),
            reason="manual_end",
            message_index=0,
        )

        self.assertTrue(summary.ended_early)
        self.assertEqual(summary.planned_minutes, 45)
        self.assertEqual(summary.focused_seconds, 1110)
        self.assertEqual(summary.pause_count, 1)
        self.assertEqual(summary.paused_seconds, 90)
        self.assertIn("本轮专注了 18 分 30 秒", summary.text)
        self.assertIn("暂停 1 次", summary.text)
        self.assertIn("没关系", summary.text)
        self.assertNotIn("上下文掉线", summary.text)

    def test_focus_summary_includes_idle_time(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=45,
            intensity=CoachingIntensity.STANDARD,
            started_at=started,
        )
        session.record_screen_still(started + timedelta(minutes=5))

        summary = build_focus_summary(
            session,
            now=started + timedelta(minutes=45),
            reason="auto_end",
            message_index=0,
        )

        self.assertEqual(summary.idle_seconds, 300)
        self.assertEqual(summary.focused_seconds, 2400)
        self.assertIn("本轮专注了 40 分钟", summary.text)
        self.assertIn("待机 5 分钟", summary.text)

    def test_focus_summary_uses_completion_praise_library(self):
        started = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        session = CoachingSession(
            goal="看学习视频",
            goal_type="学习/看文档",
            duration_minutes=25,
            intensity=CoachingIntensity.LIGHT,
            started_at=started,
        )

        summary = build_focus_summary(
            session,
            now=started + timedelta(minutes=25),
            reason="auto_end",
            message_index=1,
        )

        self.assertFalse(summary.ended_early)
        self.assertEqual(summary.focused_seconds, 1500)
        self.assertIn("完成专注", summary.text)
        self.assertIn("25 分钟", summary.text)
        self.assertNotEqual(summary.message, "陪跑结束，已生成本轮总结。")


if __name__ == "__main__":
    unittest.main()
