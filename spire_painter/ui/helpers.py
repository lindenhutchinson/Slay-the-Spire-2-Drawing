import tkinter as tk
from tkinter import ttk

from spire_painter.constants import DEFAULT_FONT, TEXT_COLOR, BG_COLOR


def flat_button(parent, text, command, state=tk.NORMAL, bg="#FFFFFF", active_bg="#EAEAEA", fg=TEXT_COLOR):
    return tk.Button(parent, text=text, command=command, state=state,
                     relief="solid", bd=1, bg=bg, fg=fg, activebackground=active_bg,
                     activeforeground=fg, font=(DEFAULT_FONT, 9), cursor="hand2")


def add_slider(parent, label, from_, to, init, command, suffix="", tooltip=None):
    """Create a labeled slider row. Returns (slider, val_label)."""
    frame = tk.Frame(parent, bg=BG_COLOR)
    frame.pack(fill="x", pady=(2, 0))
    lbl = tk.Label(frame, text=label, bg=BG_COLOR, font=(DEFAULT_FONT, 9))
    lbl.pack(side="left")
    slider = ttk.Scale(frame, from_=from_, to=to, orient="horizontal",
                       style="Blue.Horizontal.TScale", command=command)
    slider.set(init)
    slider.pack(side="left", fill="x", expand=True, padx=5)
    val_label = tk.Label(frame, text=f"{init}{suffix}", font=(DEFAULT_FONT, 10, "bold"),
                         fg="#2196F3", bg=BG_COLOR)
    val_label.pack(side="left")
    if tooltip:
        from spire_painter.tooltip import Tooltip
        Tooltip(lbl, tooltip)
        Tooltip(slider, tooltip)
    return slider, val_label


def snap_slider(slider, val_label, val, suffix=""):
    """Snap slider to integer and update label. Returns True if value changed."""
    v = round(float(val))
    if abs(float(val) - v) > 0.001:
        slider.set(v)
    current = val_label.cget("text")
    new_text = f"{v}{suffix}"
    if current != new_text:
        val_label.config(text=new_text)
        return True
    return False
