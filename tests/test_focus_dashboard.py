import json
import os
import tempfile
import unittest

from screenchat.memory.models import Conversation
from screenchat.ui.focus_dashboard import build_dashboard_payload, render_dashboard_html, write_dashboard


class FocusDashboardTests(unittest.TestCase):
    def test_payload_groups_focus_events_by_iso_week(self):
        records = [
            Conversation(
                date="2026-05-11",
                screen_summary="",
                comment="完成专注：写代码\n本轮专注了 45 分钟，计划 45 分钟。\n暂停 1 次，共 2 分钟。",
                category="coaching",
                created_at="2026-05-11T10:00:00+00:00",
                event_type="auto_end",
                target_goal="写代码",
                goal_type="写代码/修 bug",
                intensity="标准",
                planned_minutes=45,
                focused_seconds=2700,
                pause_count=1,
                ended_early=False,
            ),
            Conversation(
                date="2026-05-12",
                screen_summary="",
                comment="提前结束：看文档\n本轮专注了 18 分钟，计划 25 分钟。",
                category="coaching",
                created_at="2026-05-12T10:00:00+00:00",
                event_type="manual_end",
                target_goal="看文档",
                goal_type="学习/看文档",
                intensity="轻",
                planned_minutes=25,
                focused_seconds=1080,
                pause_count=0,
                ended_early=True,
            ),
        ]

        payload = build_dashboard_payload(records)

        self.assertEqual(payload["totals"]["sessions"], 2)
        self.assertEqual(payload["totals"]["focused_seconds"], 3780)
        self.assertEqual(payload["weeks"][0]["label"], "2026-W20")
        self.assertEqual(len(payload["weeks"][0]["stars"]), 2)
        self.assertEqual(payload["weeks"][0]["stars"][0]["brightness"], 1.0)
        self.assertLess(payload["weeks"][0]["stars"][1]["brightness"], 0.7)
        self.assertTrue(payload["weeks"][0]["stars"][0]["celestial"]["name"])
        self.assertTrue(payload["weeks"][0]["stars"][0]["celestial"]["fact"])
        self.assertIn("rarity", payload["weeks"][0]["stars"][0])

    def test_payload_backfills_duration_from_summary_text(self):
        records = [
            Conversation(
                date="2026-05-11",
                screen_summary="",
                comment="完成专注：写代码\n本轮专注了 18 分 30 秒，计划 45 分钟。\n暂停 1 次，共 2 分钟。",
                category="coaching",
                created_at="2026-05-11T10:00:00+00:00",
                event_type="auto_end",
                target_goal="写代码",
                goal_type="写代码/修 bug",
                intensity="标准",
                planned_minutes=45,
                focused_seconds=0,
                pause_count=1,
                ended_early=False,
            )
        ]

        payload = build_dashboard_payload(records)

        self.assertEqual(payload["totals"]["focused_seconds"], 1110)
        self.assertEqual(payload["weeks"][0]["stars"][0]["focused_seconds"], 1110)

    def test_longer_focus_unlocks_at_least_as_rare_celestial_body(self):
        short = Conversation(
            date="2026-05-11",
            screen_summary="",
            comment="提前结束：写代码\n本轮专注了 10 分钟，计划 45 分钟。",
            category="coaching",
            created_at="2026-05-11T10:00:00+00:00",
            event_type="manual_end",
            target_goal="短专注",
            goal_type="写代码/修 bug",
            intensity="标准",
            planned_minutes=45,
            focused_seconds=600,
            ended_early=True,
        )
        long = Conversation(
            date="2026-05-11",
            screen_summary="",
            comment="完成专注：写代码\n本轮专注了 90 分钟，计划 90 分钟。",
            category="coaching",
            created_at="2026-05-11T11:00:00+00:00",
            event_type="auto_end",
            target_goal="长专注",
            goal_type="写代码/修 bug",
            intensity="标准",
            planned_minutes=90,
            focused_seconds=5400,
            ended_early=False,
        )

        payload = build_dashboard_payload([short, long])
        stars = payload["weeks"][0]["stars"]

        self.assertGreaterEqual(stars[1]["rarity_rank"], stars[0]["rarity_rank"])
        self.assertNotEqual(stars[0]["celestial"]["name"], stars[1]["celestial"]["name"])

    def test_payload_builds_timeline_from_screen_observations(self):
        records = [
            Conversation(
                date="2026-05-13",
                screen_summary="",
                comment="开始陪跑：学视频项目",
                category="coaching",
                created_at="2026-05-13T09:00:00+00:00",
                event_type="start",
                target_goal="学视频项目",
                goal_type="学习/看文档",
                intensity="标准",
            ),
            Conversation(
                date="2026-05-13",
                screen_summary="屏幕显示视频课程和笔记窗口",
                comment="用户正在看课程并记要点。",
                category="coaching",
                created_at="2026-05-13T09:15:00+00:00",
                event_type="observation",
                coaching_state="on_track",
                target_goal="学视频项目",
                goal_type="学习/看文档",
                intensity="标准",
            ),
            Conversation(
                date="2026-05-13",
                screen_summary="浏览器切到了无关页面",
                comment="这个页面和目标不相关，要不要切回课程？",
                category="coaching",
                created_at="2026-05-13T09:30:00+00:00",
                event_type="reminder",
                coaching_state="distracted",
                target_goal="学视频项目",
                goal_type="学习/看文档",
                intensity="标准",
            ),
            Conversation(
                date="2026-05-13",
                screen_summary="",
                comment="完成专注：学视频项目\n本轮专注了 60 分钟，计划 60 分钟。",
                category="coaching",
                created_at="2026-05-13T10:00:00+00:00",
                event_type="auto_end",
                target_goal="学视频项目",
                goal_type="学习/看文档",
                intensity="标准",
                planned_minutes=60,
                focused_seconds=3600,
            ),
        ]

        payload = build_dashboard_payload(records)
        timeline = payload["weeks"][0]["stars"][0]["timeline"]

        self.assertEqual(timeline[0]["time"], "09:00")
        self.assertIn("开始陪跑", timeline[0]["text"])
        self.assertEqual(timeline[1]["time"], "09:15")
        self.assertIn("屏幕显示视频课程", timeline[1]["text"])
        self.assertEqual(timeline[2]["state"], "distracted")
        self.assertIn("完成专注", timeline[-1]["text"])

    def test_render_dashboard_embeds_payload_and_three_scene(self):
        payload = {
            "generated_at": "2026-05-12T00:00:00+00:00",
            "totals": {"sessions": 0, "focused_seconds": 0, "completed": 0, "early": 0, "pause_count": 0},
            "weeks": [],
        }

        html = render_dashboard_html(payload)

        self.assertIn("专注星图", html)
        self.assertIn("three.module.js", html)
        self.assertIn("背景星系", html)
        self.assertIn("日间 UI", html)
        self.assertIn("夜间 UI", html)
        self.assertIn("天体科普", html)
        self.assertIn("本轮专注记录", html)
        self.assertIn("focusTimeline", html)
        self.assertIn("timeline-section", html)
        self.assertIn("overflow-y: auto", html)
        self.assertIn("max-height: clamp(150px, 24vh, 280px)", html)
        self.assertIn("makeReliefTexture", html)
        self.assertIn("createSurfaceLayer", html)
        self.assertIn("emissiveIntensity: 0.06", html)
        self.assertIn("return null", html)
        self.assertIn("--panel: rgba(244, 250, 255, 0.94)", html)
        self.assertIn("let radius = 10 + t * 31", html)
        self.assertIn("weekPattern", html)
        self.assertIn("createMotionTrail", html)
        self.assertIn("createGalaxyDisc", html)
        self.assertIn("createGalaxyLabel", html)
        self.assertIn("weekDock", html)
        self.assertIn("switchWeek", html)
        self.assertIn("updateRootTarget", html)
        self.assertIn("activeGalaxyOffset", html)
        self.assertIn("focusTarget", html)
        self.assertIn("cameraDirection", html)
        self.assertIn("setCameraDistance", html)
        self.assertIn("camera.lookAt(focusTarget)", html)
        self.assertIn("targetRootPosition", html)
        self.assertNotIn("galaxyHitObjects", html)
        self.assertIn("camera.position.set(0, 38, 132)", html)
        self.assertIn("Math.min(620", html)
        self.assertIn("Math.max(6", html)
        self.assertIn("scene.fog = new THREE.FogExp2(0x02040a, 0.0026)", html)
        self.assertIn("new THREE.AmbientLight(0xb8dcff, 0.92)", html)
        self.assertIn(json.dumps(payload, ensure_ascii=False), html)

    def test_write_dashboard_creates_self_contained_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_dashboard([], output_path=os.path.join(tmp, "dashboard.html"))

            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as fh:
                html = fh.read()
            self.assertIn("专注星图", html)
            self.assertIn("window.FOCUS_GALAXY_DATA", html)


if __name__ == "__main__":
    unittest.main()
