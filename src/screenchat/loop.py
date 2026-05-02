"""
ScreenChat 的核心主循环。

和 Claude Code 的主循环同构：
  Claude Code: while True → 等用户输入 → 发 LLM → 输出结果
  ScreenChat:  while True → 等 N 秒 → 截图 → 发视觉 LLM → AI 决定是否说话

整个系统只有这一个文件在跑，没有 GUI、没有托盘、没有历史——只有终端输出。
后续所有功能（去重、托盘、聊天窗口、快捷键）都从这个循环上生长出来。
"""

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
from datetime import datetime

import imagehash

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
import mss


# ── 配置 ──────────────────────────────────────────────────

def load_config():
    """从 .env 文件读取配置，返回 dict。不做复杂抽象——够用就好。"""
    load_dotenv()
    return {
        "api_key": os.getenv("SCREENCHAT_OPENAI_API_KEY", ""),
        "model": os.getenv("SCREENCHAT_AGENT_MODEL", "kimi-k2.5"),
        "base_url": os.getenv("SCREENCHAT_OPENAI_BASE_URL", "https://api.moonshot.ai/v1"),
        "interval": int(os.getenv("SCREENCHAT_CAPTURE_INTERVAL", "20")),
        "memory_maxlen": int(os.getenv("SCREENCHAT_MEMORY_MAXLEN", "20")),
    }


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

    def __init__(self, config, comment_queue=None):
        self.config = config
        self.comment_queue = comment_queue
        self.sct = mss.MSS()
        self.client = OpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )
        self.running = True
        self.message_history = deque(maxlen=config["memory_maxlen"])  # 可配的消息序列
        self._last_dhash = None  # Layer 3: 感知哈希去重
        try:
            signal.signal(signal.SIGINT, self._on_sigint)
        except ValueError:
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
            '"category": "gaming|coding|trading|studying|writing|social|shopping|language|interview|design|health|general"}'
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
                temperature=0.3,
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
        print(f"[小幕] 启动了~ 每 {self.config['interval']} 秒看一眼屏幕")
        print("[小幕] 按 Ctrl+C 退出\n")

        while self.running:
            try:
                t0 = time.time()

                # ① 截图
                b64, img = self.capture()

                # ② Layer 3: 感知哈希去重
                dhash = imagehash.dhash(img)
                if self._last_dhash is not None and (self._last_dhash - dhash) < 5:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] · (dup)")
                    elapsed = time.time() - t0
                    sleep_time = max(0, self.config["interval"] - elapsed)
                    if self.running:
                        time.sleep(sleep_time)
                    continue
                self._last_dhash = dhash

                # ③ AI 分析
                raw = self.analyze(b64)
                result = json.loads(raw)
                ts = datetime.now().strftime("%H:%M:%S")
                if result.get("should_comment"):
                    comment = result["comment"]
                    print(f"[{ts}] 💬 {comment}")
                    # Layer 1: 追加到消息历史
                    self.message_history.append(
                        {"role": "user", "content": f"(约{self.config['interval']}秒前)"}
                    )
                    self.message_history.append(
                        {"role": "assistant", "content": comment}
                    )
                    if self.comment_queue is not None:
                        self.comment_queue.put(comment)
                    # Layer 2: 消息快满时压缩旧轮
                    self._compress_history()
                else:
                    print(f"[{ts}] ·")

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
            sleep_time = max(0, self.config["interval"] - elapsed)
            if self.running:
                time.sleep(sleep_time)


# ── 入口 ──────────────────────────────────────────────────

def main():
    config = load_config()
    if not config["api_key"] or "your-api-key" in config["api_key"]:
        print("请先在 .env 里设置 SCREENCHAT_OPENAI_API_KEY")
        sys.exit(1)

    comment_queue = queue.Queue()

    # 截图循环跑在守护线程，AI 评论通过 comment_queue 发出
    def _run_loop():
        app = ScreenChat(config, comment_queue=comment_queue)
        app.run()

    t = threading.Thread(target=_run_loop, daemon=True)
    t.start()

    # 确保 src/ 在 Python path 中
    _src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _src not in sys.path:
        sys.path.insert(0, _src)

    # 主线程给 rumps 菜单栏图标
    from screenchat.tray import icon as tray_icon
    tray_app = tray_icon.ScreenChatTray(comment_queue)
    tray_app.run()


if __name__ == "__main__":
    main()
