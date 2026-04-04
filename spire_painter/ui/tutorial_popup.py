import tkinter as tk

from spire_painter.constants import DEFAULT_FONT, TEXT_COLOR, TEXT_LIGHT, ALERT_RED


def show_tutorial(root, on_close):
    """Show first-run tutorial popup with hotkey reminders."""
    tut = tk.Toplevel(root)
    tut.overrideredirect(True)
    tut.attributes('-topmost', True)

    frame = tk.Frame(tut, bg="#FFFFFF", highlightbackground="#2196F3", highlightthickness=2)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="Welcome to Painter", font=(DEFAULT_FONT, 16, "bold"),
             bg="#FFFFFF", fg="#1976D2").pack(pady=(20, 10))
    tk.Label(frame, text="Memorize these hotkeys:", font=(DEFAULT_FONT, 10),
             bg="#FFFFFF", fg=TEXT_LIGHT).pack(pady=(0, 15))

    hk = tk.Frame(frame, bg="#F9F9F9", bd=1, relief="solid")
    hk.pack(padx=30, fill="x")
    for row, (key, desc) in enumerate([
        ("P", "Pause Drawing"),
        ("Ctrl + Alt + P", "Resume Drawing"),
        ("[", "Force Terminate"),
    ]):
        color = "#4CAF50" if "Resume" in desc else ALERT_RED
        tk.Label(hk, text=key, font=(DEFAULT_FONT, 14, "bold"), bg="#F9F9F9",
                 fg=color, width=12, anchor="e").grid(row=row, column=0, pady=10)
        tk.Label(hk, text=desc, font=(DEFAULT_FONT, 10), bg="#F9F9F9",
                 fg=TEXT_COLOR, anchor="w").grid(row=row, column=1, sticky="w", padx=10)

    def _close(event=None):
        tut.destroy()
        on_close()

    tk.Button(frame, text="Got it!", font=(DEFAULT_FONT, 11, "bold"),
              bg="#2196F3", fg="#FFFFFF", relief="flat", command=_close,
              cursor="hand2").pack(pady=(20, 20), ipadx=40, ipady=10)

    tut.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - tut.winfo_reqwidth()) // 2
    y = root.winfo_y() + (root.winfo_height() - tut.winfo_reqheight()) // 2
    tut.geometry(f"+{x}+{y}")
    tut.bind("<Escape>", _close)
    tut.focus_force()
