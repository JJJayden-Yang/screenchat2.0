

import base64
import io
import json
import os
import queue
import re
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
    CoachingSession,
    build_prompt as build_coaching_prompt,
    build_summary as build_coaching_summary,
    parse_analysis as parse_coaching_analysis,
    should_interrupt as should_coaching_interrupt,
)


# ── 配置 ──────────────────────────────────────────────────

def load_config():
    """统一配置入口：settings.json > .env > defaults。"""
    from screenchat.config import load as cfg_load
    return cfg_load()


def _extract_json(raw):
    """从 AI 返回的文本里尝试抠出 JSON。AI 有时会加 markdown 代码块或废话。"""
    if not raw:
        return None
    # 尝试 1：```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 尝试 2：从第一个 { 到最后一个 }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


# ── 主类 ──────────────────────────────────────────────────

class ScreenChat:
    """
    桌面 AI 陪伴助手的核心。

    三个步骤构成一个循环周期：
    ① capture()  — 截一张图，缩至 1280px，JPEG 压缩，base64 编码
    ② analyze()  — 发给 Kimi K2.5，让 AI 看画面决定是否说话
    ③ 打印结果   — should_comment=true 就打印评论，false 就打个点
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

    def analyze(self, image_b64):
        """
        把 base64 图片发给 Kimi K2.5，带上消息历史。

        返回值是纯 JSON 字符串：
        {"should_comment": bool, "comment": "...", "category": "..."}
        """
        prompt = (
            "你是「小幕」，一个桌面 AI 陪伴伙伴。\n"
            "你的个性：像大学室友，会吐槽、会夸你、会提醒你别上头。\n"
            "不假装是专家，不端着，不假装一直在盯着看。\n"
            "说话自然口语化，像微信聊天不是工作报告。\n\n"
            "规则：\n"
            "- 大部分时候闭嘴。只有真的注意到有趣/有用/不对劲的事才说话。\n"
            "- 如果画面很日常（桌面、浏览器首页、文件管理器）→ 不用说话。\n"
            "- 如果用户正在专注做事（打游戏团战、写代码中）→ 尽量不打扰。\n"
            "- 别说和之前重复的话。\n"
            "- 只说 1-2 句，简洁自然。\n\n"
            "只回复 JSON，不要有任何额外内容：\n"
            '{"should_comment": true或false, "comment": "如果说话，1-2句自然口语。如果不说，空字符串", '
            '"category": "gaming|coding|trading|studying|writing|social|shopping|language|interview|design|health|general", '
            '"screen_summary": "可选，20字内概括当前截图内容，方便后续记忆"}'
        )

        # 构建消息序列：system + 历史文本 + 当前图片
        messages = [{"role": "system", "content": prompt}]
        messages.extend(list(self.message_history))
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

        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=self.config["model"],
                    messages=messages,
                    temperature=1,
                    max_tokens=2000,
                )
                msg = resp.choices[0].message
                reasoning = getattr(msg, "reasoning_content", "") or ""
                if reasoning:
                    print(f"  [debug] {reasoning[:300]}...")
                raw = (msg.content or "").strip()
                if raw:
                    return raw
                return '{"should_comment": false, "comment": "", "category": "general"}'

            except Exception as e:
                err = str(e)
                if "429" in err or "overloaded" in err:
                    wait = 2 ** attempt
                    print(f"  (服务繁忙，{wait}s 后重试...)")
                    time.sleep(wait)
                    continue
                raise

        return '{"should_comment": false, "comment": "", "category": "general"}'

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
            try:
                t0 = time.time()
                session = self._current_session()
                if session is None:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] · (idle)")
                    time.sleep(self.config["capture_interval"])
                    continue

                now = datetime.now(timezone.utc)
                if session.is_expired(now):
                    if self.finish_coaching:
                        self.finish_coaching("auto_end")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💬 陪跑结束")
                    time.sleep(self.config["capture_interval"])
                    continue

                # ① 截图
                b64, img = self.capture()

                # ② Layer 3: 感知哈希去重
                dhash = imagehash.dhash(img)
                if self._last_dhash is not None and (self._last_dhash - dhash) < 5:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] · (dup)")
                    self._update_coaching_status_locked(session)
                    elapsed = time.time() - t0
                    sleep_time = max(0, self.config["capture_interval"] - elapsed)
                    if self.running:
                        time.sleep(sleep_time)
                    continue
                self._last_dhash = dhash

                # ③ 静音检查
                if self.shared.value:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] · (muted)")
                    elapsed = time.time() - t0
                    sleep_time = max(0, self.config["capture_interval"] - elapsed)
                    if self.running:
                        time.sleep(sleep_time)
                    continue

                # ④ 陪跑 AI 分析
                raw = self.analyze_coaching(b64, session)
                analysis = parse_coaching_analysis(raw)
                now = datetime.now(timezone.utc)
                self._record_coaching_state(session, analysis, now)
                decision = should_coaching_interrupt(
                    session,
                    analysis.state,
                    analysis.confidence,
                    now,
                    analysis.should_interrupt,
                    analysis.message,
                )
                ts = datetime.now().strftime("%H:%M:%S")
                if decision.allowed:
                    comment = analysis.message
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
                    if self.comment_queue is not None:
                        self.comment_queue.put(comment)
                    self._compress_history()
                else:
                    print(f"[{ts}] · ({decision.state.value}: {decision.reason})")

            except json.JSONDecodeError:
                # AI 有时不听话——试试从文本里抠 JSON
                result = _extract_json(raw)
                if result:
                    ts = datetime.now().strftime("%H:%M:%S")
                    if result.get("should_comment"):
                        print(f"[{ts}] 💬 {result['comment']}")
                    else:
                        print(f"[{ts}] ·")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠ JSON 解析失败，原始返回: {raw[:200]}")
            except Exception as e:
                # 截图失败、网络问题等都兜住，不让循环崩
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠ {e}")

            # 精确计时：用 sleep 时间补 AI 调用 + 截图耗时
            # 如果 AI 调用了 5 秒，就只 sleep 15 秒，保证总周期约 20 秒
            elapsed = time.time() - t0
            sleep_time = max(0, self.config["capture_interval"] - elapsed)
            if self.running:
                time.sleep(sleep_time)


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
        else:
            mp_coaching_status["active"] = True
            mp_coaching_status["summary"] = session.menu_summary()

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
        print(f"[小幕] 开始陪跑：{goal}（{goal_type} / {session.intensity.value} / {duration_minutes} 分钟）")

    def _finish_coaching(reason: str = "manual_end"):
        with coaching_context["lock"]:
            session = coaching_context.get("session")
            if session is None:
                _set_coaching_status(None)
                return ""
            coaching_context["session"] = None
            _set_coaching_status(None)
        summary = build_coaching_summary(session)
        event_type = "auto_end" if reason == "auto_end" else "manual_end"
        try:
            memdb.insert_coaching_event(
                event_type,
                summary,
                target_goal=session.goal,
                goal_type=session.goal_type,
                intensity=session.intensity.value,
            )
        except Exception:
            pass
        message_history.append({"role": "user", "content": f"刚结束陪跑：{session.goal}"})
        message_history.append({"role": "assistant", "content": summary})
        if mp_comment is not None:
            mp_comment.put("陪跑结束，已生成本轮总结。")
        print(f"[小幕] 陪跑结束：{session.goal}")
        return summary

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
            elif action == "coach_start":
                from screenchat.ui.coaching_window import open_coaching
                open_coaching(_start_coaching)
            elif action == "coach_stop":
                _finish_coaching("manual_end")
        except Exception:
            pass
        root.after(500, _check_ui)

    root.after(200, _check_ui)
    root.mainloop()


if __name__ == "__main__":
    main()
