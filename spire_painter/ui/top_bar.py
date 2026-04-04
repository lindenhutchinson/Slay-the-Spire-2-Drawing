import tkinter as tk

from spire_painter.constants import DEFAULT_FONT, BG_COLOR, ALERT_RED
from spire_painter.tooltip import Tooltip


class TopBar:
    """Status text, hotkey reminder, and always-on-top checkbox."""

    def __init__(self, parent, topmost_var, on_topmost_changed):
        top_bar = tk.Frame(parent, bg=BG_COLOR)
        top_bar.pack(side="top", fill="x", pady=(0, 5))

        info = tk.Frame(top_bar, bg=BG_COLOR)
        info.pack(side="right", anchor="ne")

        self.chk_topmost = tk.Checkbutton(info, text="Always on Top", font=(DEFAULT_FONT, 9),
                                          variable=topmost_var, command=on_topmost_changed, bg=BG_COLOR)
        self.chk_topmost.pack(anchor="e")
        Tooltip(self.chk_topmost, "Keep this window above all other windows.")

        tk.Label(info, text="P: Pause | Ctrl+Alt+P: Resume\n[ : Terminate",
                 fg=ALERT_RED, bg=BG_COLOR, font=(DEFAULT_FONT, 9, "bold"),
                 justify="right").pack(anchor="e", pady=(2, 0))

        self.status_text = tk.Text(top_bar, height=2, bg=BG_COLOR, fg="#1976D2",
                                   font=(DEFAULT_FONT, 10, "bold"),
                                   relief="flat", wrap="word", highlightthickness=0)
        self.status_text.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.status_text.insert("1.0", "Select an image or load existing line art...")
        self.status_text.config(state=tk.DISABLED)

    def update_status(self, msg):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert("1.0", msg)
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
