

import base64
import io
import os
import queue
import signal
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

import imagehash

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
import mss

from screenchat.coaching import (
    CoachingState,
    CoachingSession,
    build_focus_summary,
    build_prompt as build_coaching_prompt,
    fallback_intervention_message,
    idle_reminder_message,
    IDLE_CHECK_INTERVAL_SECONDS,
    parse_analysis as parse_coaching_analysis,
    should_interrupt as should_coaching_interrupt,
    valid_action_message,
)


def bounded_sleep_interval(session: CoachingSession, requested_seconds: int, now: datetime | None = None) -> int:
    """睡眠时间不能超过本轮专注剩余时间。"""
    now = now or datetime.now(timezone.utc)
    remaining = session.remaining_seconds(now)
    if remaining <= 0:
        return 0
    return max(1, min(int(requested_seconds), remaining))


# ── 配置 ──────────────────────────────────────────────────

def load_config():
    """统一配置入口：settings.json > .env > defaults。"""
    from screenchat.config import load as cfg_load
    return cfg_load()


# ── 主类 ──────────────────────────────────────────────────

class ScreenChat:
    """
    桌面 AI 陪伴助手的核心。

    活动陪跑中，三个步骤构成一个循环周期：
    ① capture()  — 截一张图，缩至 1280px，JPEG 压缩，base64 编码
    ② analyze_coaching()  — 发给模型判断目标推进状态
    ③ 打印/通知   — 只有通过提醒判定才弹出气泡
    """

    def __init__(
        self,
        config,
        comment_queue=None,
        shared_state=None,
        message_history=None,
        coaching_context=None,
        finish_coaching=None,
    ):
        self.config = config
        self.comment_queue = comment_queue
        self.shared = shared_state or {}
        self.coaching_context = coaching_context or {}
        self.finish_coaching = finish_coaching
        self.sct = mss.MSS()
        self.client = OpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )
        self.running = True
        self.message_history = message_history or deque(maxlen=config["memory_maxlen"])
        if not message_history:
            self._load_today_history()
        self._last_dhash = None
        try:
            signal.signal(signal.SIGINT, self._on_sigint)
        except ValueError:
            pass

    def _load_today_history(self):
        """启动时从 SQLite 加载今天的历史对话到 message_history。"""
        try:
            from screenchat.memory import database as memdb
            records = memdb.get_today()
            # 只加载最近的 N 条，不超过 maxlen
            for r in records[-(self.message_history.maxlen // 2):]:
                user_ctx = f"更早：{r.screen_summary}" if r.screen_summary else "(更早)"
                self.message_history.append({"role": "user", "content": user_ctx})
                self.message_history.append({"role": "assistant", "content": r.comment})
            if self.message_history:
                print(f"  (已加载今天 {len(records)} 条历史对话)")
        except Exception:
            pass

    def _on_sigint(self, signum, frame):
        """Ctrl+C 时优雅退出。"""
        print("\n[小幕] 下次见~")
        self.running = False

    # ── 步骤 ①：截图 ───────────────────────────────────

    def capture(self):
        """
        截取主显示器画面，返回 base64 字符串。

        处理链：
        mss 截取原始像素 → Pillow 转成 Image 对象
        → 缩放（max 1280px，省 token）→ JPEG 压缩（q=85，约 100KB）
        → base64 编码（可直接塞进 API 请求的 data: URL）
        """
        # mss.monitors[0] 是「所有显示器合起来」的虚拟桌面
        # mss.monitors[1] 才是主显示器
        monitor = self.sct.monitors[1]
        raw = self.sct.grab(monitor)
        # mss 返回 BGRA 格式，Pillow 要转成 RGB
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        # 缩放：长边不超过 1280px，保持宽高比
        w, h = img.size
        max_dim = 1280
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        # JPEG 压缩到内存 buffer，再 base64 编码
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8"), img

    # ── 步骤 ②：AI 分析 ───────────────────────────────

    def analyze_coaching(self, image_b64, session):
        """陪跑模式：围绕目标输出结构化状态判断。"""
        prompt = build_coaching_prompt(session)
        messages = [{"role": "system", "content": prompt}]
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}",
                        "detail": "high",
                    },
                }
            ],
        })
        resp = self.client.chat.completions.create(
            model=self.config["model"],
            messages=messages,
            temperature=1,
            max_tokens=1200,
        )
        return (resp.choices[0].message.content or "").strip()

    def _current_session(self):
        lock = self.coaching_context.get("lock")
        if lock:
            with lock:
                return self.coaching_context.get("session")
        return self.coaching_context.get("session")

    def _record_coaching_state(self, session, analysis, now):
        lock = self.coaching_context.get("lock")
        if lock:
            with lock:
                session.update_state(analysis.state, now, analysis.screen_summary)
                self._update_coaching_status_locked(session, now)
        else:
            session.update_state(analysis.state, now, analysis.screen_summary)

    def _record_coaching_reminder(self, session, message):
        lock = self.coaching_context.get("lock")
        if lock:
            with lock:
                session.record_reminder(message)
                self._update_coaching_status_locked(session)
        else:
            session.record_reminder(message)

    def _update_coaching_status_locked(self, session, now=None):
        status = self.coaching_context.get("status")
        if status is not None and session is not None:
            status["active"] = True
            status["summary"] = session.menu_summary(now)
            status["goal"] = session.goal
            status["ends_at"] = session.ends_at.isoformat()
            status["paused"] = session.is_paused(now)
            status["paused_until"] = session.paused_until.isoformat() if session.paused_until else ""
            status["pause_count"] = session.pause_count

    def _queue_comment(self, message: str, *, force: bool = False):
        if self.comment_queue is not None and message:
            if force:
                self.comment_queue.put({"message": message, "force": True})
            else:
                self.comment_queue.put(message)

    def _coaching_intervention_message(self, session, analysis) -> str:
        if valid_action_message(analysis.message):
            return analysis.message
        return fallback_intervention_message(
            session,
            analysis.state,
            analysis.screen_summary,
            analysis.target_relevance,
            analysis.suggested_action,
        )

    def _record_idle_event(self, session, now):
        idle_minutes = max(1, session.still_seconds // 60)
        summary = f"屏幕连续 {idle_minutes} 分钟未变化"
        try:
            from screenchat.memory import database as memdb
            memdb.insert_coaching_event(
                "idle",
                f"{summary}，可能离开了电脑或在看手机。",
                screen_summary=summary,
                coaching_state=CoachingState.IDLE.value,
                target_goal=session.goal,
                goal_type=session.goal_type,
                intensity=session.intensity.value,
                idle_seconds=session.total_idle_seconds,
            )
        except Exception:
            pass

    def _record_idle_reminder(self, session, now):
        message = idle_reminder_message(session)
        session.record_idle_reminder(now)
        self._record_coaching_reminder(session, message)
        self._queue_comment(message)
        try:
            from screenchat.memory import database as memdb
            memdb.insert_coaching_event(
                "reminder",
                message,
                screen_summary=f"屏幕连续 {max(1, session.still_seconds // 60)} 分钟未变化",
                coaching_state=CoachingState.IDLE.value,
                target_goal=session.goal,
                goal_type=session.goal_type,
                intensity=session.intensity.value,
                idle_seconds=session.total_idle_seconds,
            )
        except Exception:
            pass

    # ── Layer 2：场景摘要压缩 ─────────────────────────

    def _compress_history(self):
        """当消息历史接近满载时，将最早 3 轮压缩为一句摘要。"""
        maxlen = self.message_history.maxlen
        if len(self.message_history) < maxlen - 4:
            return  # 还没满，不压

        # 取最早 3 轮（6条）做素材，保留最近 2 轮不动
        old = list(self.message_history)[:6]
        recent = list(self.message_history)[6:]

        # 提取 AI 说过的话
        said = [o["content"] for o in old if o["role"] == "assistant"]
        prompt = (
            "把以下 AI 陪伴助手对用户说过的话压缩为一句 20-30 字的简洁摘要。\n"
            "只写摘要本身，不要多余内容。\n\n"
            + "\n".join(f"- {s}" for s in said)
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.config["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=1,
                max_tokens=60,
            )
            summary = resp.choices[0].message.content.strip()
        except Exception:
            summary = "刚才聊了几句。"

        # 重建：压缩摘要 + 最近轮次
        self.message_history.clear()
        self.message_history.append({"role": "user", "content": "(稍早前)"})
        self.message_history.append({"role": "assistant", "content": summary})
        for item in recent:
            self.message_history.append(item)

    # ── 步骤 ③：主循环 ─────────────────────────────────

    def run(self):
        """
        启动伴随循环。

        和 Claude Code 的 while-true 主循环完全同构：
        - Claude Code：等 stdin → 发 LLM → 打 stdout
        - ScreenChat：等 sleep → 截图 → 调 AI → 打终端

        如果 AI 决定说话就打印评论，不说就打印一个 · 表示本轮在安静运行。
        """
        print(f"[小幕] 启动了~ 每 {self.config['capture_interval']} 秒看一眼屏幕")
        print("[小幕] 按 Ctrl+C 退出\n")

        while self.running:
            sleep_interval = self.config["capture_interval"]
            try:
                t0 = time.time()
                session = self._current_session()
                if session is None:
                    time.sleep(self.config["capture_interval"])
                    continue

                now = datetime.now(timezone.utc)
                if session.is_expired(now):
                    if self.finish_coaching:
                        self.finish_coaching("auto_end")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💬 陪跑结束")
                    time.sleep(1)
                    continue
                sleep_interval = session.check_interval_seconds
                if session.is_paused(now):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] · (paused)")
                    self._update_coaching_status_locked(session, now)
                    pause_sleep = min(10, max(1, int((session.paused_until - now).total_seconds())))
                    time.sleep(bounded_sleep_interval(session, pause_sleep, now))
                    continue

                # ① 截图
                b64, img = self.capture()

                # ② Layer 3: 感知哈希去重
                dhash = imagehash.dhash(img)
                if self._last_dhash is not None and (self._last_dhash - dhash) < 5:
                    now = datetime.now(timezone.utc)
                    session.record_screen_still(now)
                    idle_minutes = max(1, session.still_seconds // 60)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] · (idle: 屏幕未变化 {idle_minutes} 分钟)")
                    self._record_idle_event(session, now)
                    if session.idle_reminder_due(now):
                        self._record_idle_reminder(session, now)
                    sleep_interval = IDLE_CHECK_INTERVAL_SECONDS
                    self._update_coaching_status_locked(session, now)
                    if self.running:
                        time.sleep(bounded_sleep_interval(session, sleep_interval))
                    continue
                self._last_dhash = dhash
                session.record_screen_change(datetime.now(timezone.utc))

                # ③ 静音检查
                if self.shared.value:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] · (muted)")
                    if self.running:
                        time.sleep(bounded_sleep_interval(session, sleep_interval))
                    continue

                # ④ 陪跑 AI 分析
                raw = self.analyze_coaching(b64, session)
                analysis = parse_coaching_analysis(raw)
                now = datetime.now(timezone.utc)
                self._record_coaching_state(session, analysis, now)
                try:
                    from screenchat.memory import database as memdb
                    if analysis.screen_summary:
                        memdb.insert_coaching_event(
                            "observation",
                            analysis.target_relevance or analysis.screen_summary,
                            screen_summary=analysis.screen_summary,
                            coaching_state=analysis.state.value,
                            target_relevance=analysis.target_relevance,
                            suggested_action=analysis.suggested_action,
                            target_goal=session.goal,
                            goal_type=session.goal_type,
                            intensity=session.intensity.value,
                        )
                except Exception:
                    pass
                decision = should_coaching_interrupt(
                    session,
                    analysis.state,
                    analysis.confidence,
                    now,
                    analysis.should_interrupt,
                    self._coaching_intervention_message(session, analysis),
                )
                ts = datetime.now().strftime("%H:%M:%S")
                if decision.allowed:
                    comment = self._coaching_intervention_message(session, analysis)
                    print(f"[{ts}] 💬 {comment}")
                    user_ctx = f"陪跑观察：{analysis.screen_summary}" if analysis.screen_summary else "陪跑观察"
                    self.message_history.append({"role": "user", "content": user_ctx})
                    self.message_history.append({"role": "assistant", "content": comment})
                    self._record_coaching_reminder(session, comment)
                    try:
                        from screenchat.memory import database as memdb
                        memdb.insert_coaching_event(
                            "reminder",
                            comment,
                            screen_summary=analysis.screen_summary,
                            coaching_state=analysis.state.value,
                            target_relevance=analysis.target_relevance,
                            suggested_action=analysis.suggested_action,
                            target_goal=session.goal,
                            goal_type=session.goal_type,
                            intensity=session.intensity.value,
                        )
                    except Exception:
                        pass
                    self._queue_comment(comment)
                    self._compress_history()
                else:
                    print(f"[{ts}] · ({decision.state.value}: {decision.reason})")
                session.advance_check_interval(decision.state)
                sleep_interval = session.check_interval_seconds

            except Exception as e:
                # 截图失败、网络问题等都兜住，不让循环崩
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠ {e}")

            if self.running:
                session = self._current_session()
                if session is None:
                    time.sleep(sleep_interval)
                else:
                    time.sleep(bounded_sleep_interval(session, sleep_interval))


# ── 入口 ──────────────────────────────────────────────────

def main():
    _src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _src not in sys.path:
        sys.path.insert(0, _src)

    config = load_config()
    if not config["api_key"] or "your-api-key" in config["api_key"]:
        print("请先在 .env 或设置中配置 API Key")
        sys.exit(1)

    from screenchat.memory import database as memdb
    memdb.init()

    import multiprocessing
    mp_comment = multiprocessing.Queue()
    mp_ui = multiprocessing.Queue()
    mp_muted = multiprocessing.Value('b', config.get("muted", False))
    manager = multiprocessing.Manager()
    mp_coaching_status = manager.dict({"active": False, "summary": ""})

    # 在子线程里 mute 直接读 mp_muted.value
    shared = mp_muted
    message_history = deque(maxlen=config["memory_maxlen"])
    coaching_context = {
        "session": None,
        "lock": threading.Lock(),
        "status": mp_coaching_status,
    }
    # 加载今天历史
    try:
        records = memdb.get_today()
        for r in records[-(config["memory_maxlen"] // 2):]:
            ctx = f"更早：{r.screen_summary}" if r.screen_summary else "(更早)"
            message_history.append({"role": "user", "content": ctx})
            message_history.append({"role": "assistant", "content": r.comment})
    except Exception:
        pass

    def _set_coaching_status(session):
        if session is None:
            mp_coaching_status["active"] = False
            mp_coaching_status["summary"] = ""
            mp_coaching_status["goal"] = ""
            mp_coaching_status["ends_at"] = ""
            mp_coaching_status["paused"] = False
            mp_coaching_status["paused_until"] = ""
            mp_coaching_status["pause_count"] = 0
        else:
            mp_coaching_status["active"] = True
            mp_coaching_status["summary"] = session.menu_summary()
            mp_coaching_status["goal"] = session.goal
            mp_coaching_status["ends_at"] = session.ends_at.isoformat()
            mp_coaching_status["paused"] = session.is_paused()
            mp_coaching_status["paused_until"] = session.paused_until.isoformat() if session.paused_until else ""
            mp_coaching_status["pause_count"] = session.pause_count

    def _start_coaching(goal: str, goal_type: str, duration_minutes: int, intensity: str):
        session = CoachingSession(
            goal=goal,
            goal_type=goal_type,
            duration_minutes=duration_minutes,
            intensity=intensity,
            started_at=datetime.now(timezone.utc),
        )
        with coaching_context["lock"]:
            coaching_context["session"] = session
            _set_coaching_status(session)
        try:
            memdb.insert_coaching_event(
                "start",
                f"开始陪跑：{goal}",
                target_goal=goal,
                goal_type=goal_type,
                intensity=session.intensity.value,
            )
        except Exception:
            pass
        if mp_comment is not None:
            mp_comment.put(f"开始陪跑：{goal}（{duration_minutes} 分钟，{session.intensity.value}）")
        print(f"[小幕] 开始陪跑：{goal}（{goal_type} / {session.intensity.value} / {duration_minutes} 分钟）")

    def _finish_coaching(reason: str = "manual_end"):
        with coaching_context["lock"]:
            session = coaching_context.get("session")
            if session is None:
                _set_coaching_status(None)
                return ""
            coaching_context["session"] = None
            _set_coaching_status(None)
        now = datetime.now(timezone.utc)
        summary = build_focus_summary(session, now=now, reason=reason)
        event_type = "auto_end" if reason == "auto_end" else "manual_end"
        try:
            memdb.insert_coaching_event(
                event_type,
                summary.text,
                target_goal=session.goal,
                goal_type=session.goal_type,
                intensity=session.intensity.value,
                planned_minutes=summary.planned_minutes,
                focused_seconds=summary.focused_seconds,
                pause_count=summary.pause_count,
                idle_seconds=summary.idle_seconds,
                ended_early=summary.ended_early,
            )
        except Exception:
            pass
        message_history.append({"role": "user", "content": f"刚结束陪跑：{session.goal}"})
        message_history.append({"role": "assistant", "content": summary.text})
        if mp_comment is not None:
            mp_comment.put({"message": summary.message, "force": True})
        print(f"[小幕] 陪跑结束：{session.goal}")
        return summary.text

    def _toggle_pause_coaching():
        with coaching_context["lock"]:
            session = coaching_context.get("session")
            if session is None:
                return
            now = datetime.now(timezone.utc)
            if session.is_paused(now):
                session.resume(now)
                message = "继续专注，小幕回到陪跑状态。"
            elif session.pause(now):
                message = f"已暂停专注 2 分钟（本轮第 {session.pause_count}/2 次）。"
            else:
                message = "本轮暂停次数已经用完啦，先把这一小段收个尾。"
            _set_coaching_status(session)
        if mp_comment is not None:
            mp_comment.put(message)
        print(f"[小幕] {message}")

    def _run_loop():
        app = ScreenChat(config, comment_queue=mp_comment,
                         shared_state=shared,
                         message_history=message_history,
                         coaching_context=coaching_context,
                         finish_coaching=_finish_coaching)
        app.run()

    t = threading.Thread(target=_run_loop, daemon=True)
    t.start()

    # rumps 进子进程，customtkinter 占主线程
    from screenchat.tray.icon import run_tray
    tray_proc = multiprocessing.Process(
        target=run_tray,
        args=(mp_comment, mp_ui, mp_muted, _src, mp_coaching_status),
        daemon=True,
    )
    tray_proc.start()

    # 共享客户端（给聊天窗口用）
    shared_client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
    )
    shared_sct = mss.MSS()

    def _capture_for_chat():
        """聊天窗口用的截图函数。"""
        monitor = shared_sct.monitors[1]
        raw = shared_sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        w, h = img.size
        if max(w, h) > 1280:
            ratio = 1280 / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _send_chat(text: str, attach_screenshot: bool = False) -> str:
        """聊天回调：用户文本 → Kimi 回复。默认不带截图省钱。"""
        messages_for_ai = [
            {"role": "system", "content": (
                "你是「小幕」，一个桌面 AI 陪伴伙伴。"
                "你的个性：像大学室友，会吐槽、会夸你、会提醒你别上头。"
                "说话自然口语化，像微信聊天。"
            )},
        ]
        for item in list(message_history):
            messages_for_ai.append(
                {"role": item["role"], "content": item["content"]})
        # 用户消息
        user_content = []
        user_content.append({"type": "text", "text": text})
        if attach_screenshot:
            b64 = _capture_for_chat()
            user_content.append(
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}", "detail": "high"}})
        messages_for_ai.append({"role": "user", "content": user_content})
        resp = shared_client.chat.completions.create(
            model=config["model"], messages=messages_for_ai,
            temperature=1, max_tokens=2000,
        )
        reply = resp.choices[0].message.content.strip()
        # Persist
        try:
            memdb.insert("", text, "general", role="user")
            memdb.insert("", reply, "general", role="assistant")
        except Exception:
            pass
        return reply

    import customtkinter as ctk
    root = ctk.CTk()
    root.withdraw()

    def _check_ui():
        try:
            action = mp_ui.get_nowait()
            if action == "chat":
                from screenchat.ui.chat_window import open_chat
                open_chat(lambda t, f=False: _send_chat(t, f))
            elif action == "settings":
                from screenchat.ui.settings_window import open_settings
                open_settings()
            elif action == "focus_dashboard":
                from screenchat.memory import database as memdb
                from screenchat.ui.focus_dashboard import open_dashboard
                memdb.init()
                open_dashboard(memdb.get_all())
            elif action == "coach_start":
                from screenchat.ui.coaching_window import open_coaching
                open_coaching(_start_coaching)
            elif action == "coach_stop":
                _finish_coaching("manual_end")
            elif action == "coach_pause_toggle":
                _toggle_pause_coaching()
        except Exception:
            pass
        root.after(500, _check_ui)

    root.after(200, _check_ui)
    root.mainloop()


if __name__ == "__main__":
    main()
