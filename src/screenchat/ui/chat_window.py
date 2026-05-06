import threading
import customtkinter as ctk

from screenchat.memory import database as memdb

# 颜色方案 — 深色科技风
BG_MSG = "#1E1E2E"
CHAT_BG = "#181825"
USER_BUBBLE = "#3B82F6"   # 蓝色
AI_BUBBLE = "#2D2D3F"     # 深灰紫
TEXT_COLOR = "#E4E4EC"
META_COLOR = "#6C6C8A"
INPUT_BG = "#252537"
ACCENT = "#3B82F6"


def open_chat(send_callback):
    win = ctk.CTkToplevel()
    win.title("小幕 — 对话")
    win.geometry("480x560")
    win.resizable(True, True)
    win.configure(fg_color=CHAT_BG)

    # ── 消息区域 ──
    msg_frame = ctk.CTkScrollableFrame(win, width=440, height=380,
                                       fg_color=CHAT_BG)
    msg_frame.pack(padx=16, pady=(16, 4), fill="both", expand=True)

    # 加载历史
    records = memdb.get_today()
    if records:
        for r in records:
            ts = r.created_at[11:16] if "T" in r.created_at else ""
            _bubble(msg_frame, r.comment, r.role, ts, r.screen_summary)
    else:
        ctk.CTkLabel(msg_frame, text="今天还没有对话，开始聊聊吧",
                     font=ctk.CTkFont(size=13), text_color=META_COLOR).pack(pady=40)

    # ── 输入区域 ──
    input_bar = ctk.CTkFrame(win, fg_color=CHAT_BG)
    input_bar.pack(fill="x", padx=16, pady=(4, 12))

    entry = ctk.CTkEntry(input_bar, placeholder_text="输入消息...",
                         fg_color=INPUT_BG, border_width=0,
                         height=38, font=ctk.CTkFont(size=13))
    entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

    attach_var = ctk.BooleanVar(value=False)
    attach_cb = ctk.CTkCheckBox(input_bar, text="📎 截图", variable=attach_var,
                                font=ctk.CTkFont(size=11), text_color=META_COLOR,
                                fg_color=ACCENT, border_width=1.5,
                                width=20, height=20)
    attach_cb.pack(side="left", padx=(0, 6))

    send_btn = ctk.CTkButton(input_bar, text="发送", width=56,
                             fg_color=ACCENT, hover_color="#2563EB",
                             font=ctk.CTkFont(size=13, weight="bold"))

    # loading 动画
    loading_label = None

    def _show_loading():
        nonlocal loading_label
        if loading_label is None:
            loading_label = ctk.CTkLabel(
                msg_frame, text="小幕正在思考...",
                font=ctk.CTkFont(size=12), text_color=META_COLOR)
            loading_label.pack(pady=6)
        msg_frame._parent_canvas.yview_moveto(1)

    def _hide_loading():
        nonlocal loading_label
        if loading_label:
            loading_label.destroy()
            loading_label = None

    def _do_send():
        nonlocal loading_label
        text = entry.get().strip()
        if not text:
            return
        entry.delete(0, "end")
        entry.configure(state="disabled")
        send_btn.configure(state="disabled", text="...")

        _bubble(msg_frame, text, "user")
        _show_loading()

        def _call():
            try:
                reply = send_callback(text, attach_var.get())
            except Exception as e:
                reply = f"(出错了: {e})"
            # 回主线程更新 UI
            win.after(0, lambda: _on_reply(reply))

        threading.Thread(target=_call, daemon=True).start()

    def _on_reply(reply):
        _hide_loading()
        _bubble(msg_frame, reply, "assistant")
        entry.configure(state="normal")
        send_btn.configure(state="normal", text="发送")
        entry.focus()

    send_btn.configure(command=_do_send)
    entry.bind("<Return>", lambda e: _do_send())

    win.after(100, lambda: entry.focus())


def _bubble(frame, text, role, timestamp="", extra=""):
    """渲染一条消息气泡。"""
    row = ctk.CTkFrame(frame, fg_color="transparent")
    row.pack(fill="x", pady=3, padx=4)

    is_user = (role == "user")
    align = "e" if is_user else "w"

    bubble_frame = ctk.CTkFrame(
        row,
        fg_color=USER_BUBBLE if is_user else AI_BUBBLE,
        corner_radius=12,
    )
    bubble_frame.pack(anchor=align, padx=4)

    inner = ctk.CTkFrame(bubble_frame, fg_color="transparent")
    inner.pack(padx=10, pady=(6, 8))

    if not is_user and extra:
        ctk.CTkLabel(inner, text=f"{timestamp}  {extra}",
                     font=ctk.CTkFont(size=10),
                     text_color=META_COLOR).pack(anchor="w")

    ctk.CTkLabel(
        inner, text=text,
        font=ctk.CTkFont(size=13),
        wraplength=340, justify="left",
        text_color=TEXT_COLOR,
    ).pack(anchor="w")
