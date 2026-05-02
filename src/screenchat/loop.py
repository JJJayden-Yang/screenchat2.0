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
import re
import signal
import sys
import time
from datetime import datetime

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

    def __init__(self, config):
        self.config = config
        # MSS 是跨平台截图库，性能比 PIL ImageGrab 好得多
        self.sct = mss.MSS()
        # OpenAI SDK 配上 Moonshot 的 base_url，代码不变、模型换成 Kimi
        self.client = OpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )
        self.running = True
        # 注册 Ctrl+C 信号处理器，确保退出时打印告别语
        signal.signal(signal.SIGINT, self._on_sigint)

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
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # ── 步骤 ②：AI 分析 ───────────────────────────────

    def analyze(self, image_b64):
        """
        把 base64 图片发给 Kimi K2.5，让 AI 看画面 + 决定是否说话。

        返回值是纯 JSON 字符串，格式：
        {"should_comment": bool, "comment": "评论内容", "category": "场景分类"}

        如果服务端过载（429），自动退避重试，最多 3 次。
        全部重试失败就返回默认 JSON（不说话）。
        """
        # 系统 prompt 定义「小幕」的朋友型人格
        prompt = (
            "你是「小幕」，一个桌面 AI 陪伴伙伴。\n"
            "你的个性：像大学室友，会吐槽、会夸你、会提醒你别上头。\n"
            "不假装是专家，不端着，不假装一直在盯着看。\n"
            "说话自然口语化，像微信聊天不是工作报告。\n\n"
            "规则：\n"
            "- 大部分时候闭嘴。只有真的注意到有趣/有用/不对劲的事才说话。\n"
            "- 如果画面很日常（桌面、浏览器首页、文件管理器）→ 不用说话。\n"
            "- 如果用户正在专注做事（打游戏团战、写代码中）→ 尽量不打扰。\n"
            "- 只说 1-2 句，简洁自然。\n\n"
            "只回复 JSON，不要有任何额外内容：\n"
            '{"should_comment": true或false, "comment": "如果说话，1-2句自然口语。如果不说，空字符串", '
            '"category": "gaming|coding|trading|studying|writing|social|shopping|language|interview|design|health|general"}'
        )

        # 最多重试 3 次，应对 Moonshot 服务端偶发过载
        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=self.config["model"],
                    messages=[
                        {"role": "system", "content": prompt},
                        {
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
                        },
                    ],
                    temperature=1,
                    max_tokens=2000,  # Kimi reasoning 吃 token，给够空间让 JSON 完整输出
                )
                msg = resp.choices[0].message
                # 优先用 content；若 AI 仍走了 reasoning 导致 content 空，则兜底
                raw = (msg.content or "").strip()
                if raw:
                    return raw
                # content 空 → silent
                return '{"should_comment": false, "comment": "", "category": "general"}'

            except Exception as e:
                err = str(e)
                # 429 = 服务端过载，等一会儿重试
                if "429" in err or "overloaded" in err:
                    wait = 2 ** attempt  # 指数退避：1s → 2s → 4s
                    print(f"  (服务繁忙，{wait}s 后重试...)")
                    time.sleep(wait)
                    continue
                raise

        # 全部重试都失败了，就当没什么可说的
        return '{"should_comment": false, "comment": "", "category": "general"}'

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
                b64 = self.capture()
                # ② AI 分析
                raw = self.analyze(b64)
                # ③ 解析 AI 返回的 JSON，决定是否打印
                result = json.loads(raw)
                ts = datetime.now().strftime("%H:%M:%S")
                if result.get("should_comment"):
                    print(f"[{ts}] 💬 {result['comment']}")
                else:
                    # · 表示本轮有在跑，但 AI 觉得不需要说话
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

    app = ScreenChat(config)
    app.run()


if __name__ == "__main__":
    main()
