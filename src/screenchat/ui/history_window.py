import customtkinter as ctk

from screenchat.memory.database import get_today


def open_history():
    """打开今日对话记录窗口。"""
    records = get_today()

    win = ctk.CTkToplevel()
    win.title("小幕 — 今日记录")
    win.geometry("440x520")
    win.resizable(True, True)

    header = ctk.CTkLabel(win, text="小幕 — 今日记录", font=ctk.CTkFont(size=16, weight="bold"))
    header.pack(pady=(16, 8))

    frame = ctk.CTkScrollableFrame(win, width=400, height=420)
    frame.pack(padx=16, pady=8, fill="both", expand=True)

    if not records:
        ctk.CTkLabel(frame, text="今天还没有聊天记录",
                     font=ctk.CTkFont(size=13)).pack(pady=40)
    else:
        for r in records:
            # 一行记录：时间 + 场景 + 评论
            ts = r.created_at[11:16] if "T" in r.created_at else r.created_at[-8:-3]
            line = ctk.CTkFrame(frame, fg_color="transparent")
            line.pack(fill="x", pady=4)

            meta = f"{ts}"
            if r.screen_summary:
                meta += f"  ·  {r.screen_summary}"
            ctk.CTkLabel(line, text=meta, font=ctk.CTkFont(size=11),
                         text_color="gray").pack(anchor="w")

            ctk.CTkLabel(line, text=r.comment, font=ctk.CTkFont(size=13),
                         wraplength=380, justify="left").pack(anchor="w", pady=(1, 6))

    win.after(100, win.focus)
