import os
import queue
import subprocess
import threading

import rumps


def _send_notification(comment: str):
    """通过 osascript 发 macOS 原生通知，走系统通知中心。"""
    safe = comment.replace('"', "'").replace("\n", " ")
    subprocess.run([
        "osascript", "-e",
        f'display notification "{safe}" with title "小幕"',
    ], capture_output=True)


class ScreenChatTray(rumps.App):
    """菜单栏图标 + 下拉菜单 + 气泡通知。rumps 在主线程运行。"""

    def __init__(self, comment_queue: queue.Queue):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        super().__init__(
            name="小幕",
            title="小幕",
            icon=icon_path,
        )
        self.comment_queue = comment_queue

        # 菜单
        self.menu = [
            rumps.MenuItem("最近记录...", callback=self._on_history),
            rumps.MenuItem("偏好设置...", callback=self._on_settings),
            None,  # 分隔线
            rumps.MenuItem("退出", callback=lambda _: rumps.quit_application()),
        ]

        # 定时检查队列，有新消息就发通知
        rumps.Timer(self._check_queue, 0.5).start()

    def _check_queue(self, _timer):
        """rumps Timer 回调：检查队列，有 AI 评论就弹通知。"""
        try:
            comment = self.comment_queue.get_nowait()
            _send_notification(comment)
        except queue.Empty:
            pass

    def _on_history(self, _sender):
        print("[小幕] TODO: 打开最近记录")

    def _on_settings(self, _sender):
        print("[小幕] TODO: 打开偏好设置")
