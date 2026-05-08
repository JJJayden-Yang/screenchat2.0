import customtkinter as ctk


GOAL_TYPES = ["写代码/修 bug", "学习/看文档", "防走神", "自定义"]
INTENSITIES = ["轻", "标准", "严格"]
DURATIONS = ["25", "45", "60", "自定义"]


def open_coaching(on_start):
    """打开开始陪跑窗口。"""
    win = ctk.CTkToplevel()
    win.title("开始陪跑")
    win.geometry("440x420")
    win.resizable(False, False)

    ctk.CTkLabel(win, text="本轮目标").pack(anchor="w", padx=20, pady=(18, 4))
    goal_var = ctk.StringVar()
    goal_entry = ctk.CTkEntry(
        win,
        textvariable=goal_var,
        width=400,
        placeholder_text="例如：45 分钟修完启动报错",
    )
    goal_entry.pack(padx=20)

    ctk.CTkLabel(win, text="目标类型").pack(anchor="w", padx=20, pady=(14, 4))
    goal_type_var = ctk.StringVar(value=GOAL_TYPES[0])
    ctk.CTkOptionMenu(win, values=GOAL_TYPES, variable=goal_type_var, width=400).pack(padx=20)

    ctk.CTkLabel(win, text="时长").pack(anchor="w", padx=20, pady=(14, 4))
    duration_frame = ctk.CTkFrame(win, fg_color="transparent")
    duration_frame.pack(fill="x", padx=20)
    duration_var = ctk.StringVar(value="45")
    duration_menu = ctk.CTkOptionMenu(duration_frame, values=DURATIONS, variable=duration_var, width=190)
    duration_menu.pack(side="left")
    custom_duration_var = ctk.StringVar(value="45")
    custom_duration = ctk.CTkEntry(duration_frame, textvariable=custom_duration_var, width=190)
    custom_duration.pack(side="right")

    ctk.CTkLabel(win, text="强度").pack(anchor="w", padx=20, pady=(14, 4))
    intensity_var = ctk.StringVar(value="标准")
    ctk.CTkSegmentedButton(win, values=INTENSITIES, variable=intensity_var, width=400).pack(padx=20)

    error_var = ctk.StringVar(value="")
    ctk.CTkLabel(win, textvariable=error_var, text_color="#EF4444").pack(anchor="w", padx=20, pady=(12, 0))

    def _selected_duration():
        raw = custom_duration_var.get() if duration_var.get() == "自定义" else duration_var.get()
        try:
            minutes = int(raw)
        except ValueError:
            minutes = 0
        return minutes

    def _start():
        goal = goal_var.get().strip()
        minutes = _selected_duration()
        if not goal:
            error_var.set("先写一个具体目标，小幕才知道该陪你盯什么。")
            return
        if minutes <= 0:
            error_var.set("时长需要是大于 0 的分钟数。")
            return
        on_start(goal, goal_type_var.get(), minutes, intensity_var.get())
        win.destroy()

    ctk.CTkButton(win, text="开始", command=_start, width=160).pack(pady=18)
    win.after(100, goal_entry.focus)
