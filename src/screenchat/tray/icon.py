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

    def __init__(self, comment_queue, ui_queue, muted_val, coaching_status=None):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        super().__init__(name="小幕", title="小幕", icon=icon_path, quit_button=None)
        self.comment_queue = comment_queue
        self.ui_queue = ui_queue
        self.muted_val = muted_val  # multiprocessing.Value('b')
        self.coaching_status = coaching_status

        self._build_menu()
        rumps.Timer(self._check_queue, 0.5).start()
        rumps.Timer(self._refresh_menu, 2).start()

    def _build_menu(self):
        # rumps 的 App.menu setter 是 update 语义，不会替换旧菜单。
        # 定时刷新前必须先清空，否则菜单项会每 2 秒追加一遍。
        self._menu.clear()
        label = "恢复提醒" if self.muted_val.value else "暂停提醒"
        mute_item = rumps.MenuItem(label, callback=self._on_toggle_mute)
        items = []
        if self._coaching_active():
            summary = self.coaching_status.get("summary", "陪跑中")
            status_item = rumps.MenuItem(summary, callback=None)
            items.extend([
                status_item,
                rumps.MenuItem("结束陪跑", callback=self._on_stop_coaching),
                None,
            ])
        else:
            items.append(rumps.MenuItem("开始陪跑...", callback=self._on_start_coaching))
        items.extend([
            mute_item,
            rumps.MenuItem("对话...", callback=self._on_chat),
            rumps.MenuItem("偏好设置...", callback=self._on_settings),
            None,
            rumps.MenuItem("退出", callback=lambda _: rumps.quit_application()),
        ])
        self.menu = items

    def _coaching_active(self):
        try:
            return bool(self.coaching_status and self.coaching_status.get("active", False))
        except Exception:
            return False

    def _refresh_menu(self, _timer):
        self._build_menu()

    def _on_toggle_mute(self, sender):
        self.muted_val.value = not self.muted_val.value
        sender.title = "恢复提醒" if self.muted_val.value else "暂停提醒"

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

    def _on_start_coaching(self, _sender):
        if self.ui_queue:
            self.ui_queue.put("coach_start")

    def _on_stop_coaching(self, _sender):
        if self.ui_queue:
            self.ui_queue.put("coach_stop")


def run_tray(comment_queue, ui_queue, muted_val, src_path, coaching_status=None):
    """子进程入口：跑 rumps 托盘。"""
    import sys as _sys
    if src_path not in _sys.path:
        _sys.path.insert(0, src_path)
    app = ScreenChatTray(comment_queue, ui_queue, muted_val, coaching_status)
    app.run()
