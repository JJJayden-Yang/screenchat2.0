import customtkinter as ctk

from screenchat.config import load, save


def open_settings():
    """打开偏好设置窗口。"""
    config = load()
    win = ctk.CTkToplevel()
    win.title("偏好设置")
    win.geometry("400x320")
    win.resizable(False, False)

    # ── API Key ──
    ctk.CTkLabel(win, text="API Key").pack(anchor="w", padx=20, pady=(16, 2))
    _orig_key = config["api_key"]
    key_var = ctk.StringVar(value=_orig_key)
    key_entry = ctk.CTkEntry(win, textvariable=key_var, show="*", width=360)
    key_entry.pack(padx=20)

    # ── 截图间隔 ──
    ctk.CTkLabel(win, text="截图间隔 (秒)").pack(anchor="w", padx=20, pady=(12, 2))
    interval_var = ctk.StringVar(value=str(config["capture_interval"]))
    ctk.CTkEntry(win, textvariable=interval_var, width=360).pack(padx=20)

    # ── 记忆长度 ──
    ctk.CTkLabel(win, text="记忆长度 (条)").pack(anchor="w", padx=20, pady=(12, 2))
    mem_var = ctk.StringVar(value=str(config["memory_maxlen"]))
    ctk.CTkEntry(win, textvariable=mem_var, width=360).pack(padx=20)

    def on_save():
        new_key = key_var.get()
        if new_key and new_key != _orig_key:
            save("api_key", new_key)
        save("capture_interval", int(interval_var.get() or "20"))
        save("memory_maxlen", int(mem_var.get() or "20"))
        win.destroy()
        # 提示重启生效
        import subprocess
        subprocess.run([
            "osascript", "-e",
            'display notification "设置已保存，下次启动 ScreenChat 时生效" with title "小幕"',
        ], capture_output=True)

    btn = ctk.CTkButton(win, text="保存", command=on_save, width=160)
    btn.pack(pady=24)

    # 让窗口获得焦点
    win.after(100, win.focus)
