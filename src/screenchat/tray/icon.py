import os
import subprocess

import rumps


def _send_notification(comment: str):
    """通过 osascript 发 macOS 原生通知。"""
    safe = comment.replace('"', "'").replace("\n", " ")
    subprocess.run([
        "osascript", "-e",
        f'display notification "{safe}" with title "小幕"',
    ], capture_output=True)


class ScreenChatTray(rumps.App):
    """菜单栏图标 + 下拉菜单 + 气泡通知。在子进程中跑。"""

    def __init__(self, comment_queue, ui_queue, muted_val):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        super().__init__(name="小幕", title="小幕", icon=icon_path, quit_button=None)
        self.comment_queue = comment_queue
        self.ui_queue = ui_queue
        self.muted_val = muted_val  # multiprocessing.Value('b')

        self._build_menu()
        rumps.Timer(self._check_queue, 0.5).start()

    def _build_menu(self):
        label = "🔇 已静音" if self.muted_val.value else "🔊 收听中"
        mute_item = rumps.MenuItem(label, callback=self._on_toggle_mute)
        self.menu = [
            mute_item,
            rumps.MenuItem("对话...", callback=self._on_chat),
            rumps.MenuItem("偏好设置...", callback=self._on_settings),
            None,
            rumps.MenuItem("退出", callback=lambda _: rumps.quit_application()),
        ]

    def _on_toggle_mute(self, sender):
        self.muted_val.value = not self.muted_val.value
        sender.title = "🔇 已静音" if self.muted_val.value else "🔊 收听中"

    def _check_queue(self, _timer):
        """检查多进程队列，有 AI 评论就弹通知（静音时跳过）。"""
        try:
            comment = self.comment_queue.get_nowait()
            if not self.muted_val.value:
                _send_notification(comment)
        except Exception:
            pass

    def _on_chat(self, _sender):
        if self.ui_queue:
            self.ui_queue.put("chat")

    def _on_settings(self, _sender):
        if self.ui_queue:
            self.ui_queue.put("settings")


def run_tray(comment_queue, ui_queue, muted_val, src_path):
    """子进程入口：跑 rumps 托盘。"""
    import sys as _sys
    if src_path not in _sys.path:
        _sys.path.insert(0, src_path)
    app = ScreenChatTray(comment_queue, ui_queue, muted_val)
    app.run()
