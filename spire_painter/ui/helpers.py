import tkinter as tk
from tkinter import ttk

from spire_painter.constants import DEFAULT_FONT, TEXT_COLOR, BG_COLOR


def flat_button(parent, text, command, state=tk.NORMAL, bg="#FFFFFF", active_bg="#EAEAEA", fg=TEXT_COLOR):
    return tk.Button(parent, text=text, command=command, state=state,
                     relief="solid", bd=1, bg=bg, fg=fg, activebackground=active_bg,
                     activeforeground=fg, font=(DEFAULT_FONT, 9), cursor="hand2")


def add_slider(parent, label, from_, to, init, command, suffix="", tooltip=None):
    """Create a labeled slider with an editable number entry.

    The slider has a fixed range for quick adjustment. The entry accepts any
    integer, allowing values beyond the slider's range. Editing the entry
    updates the slider (clamped) and fires the command callback.

    Returns (slider, entry, val_var) where val_var is a StringVar holding the
    current display value.
    """
    frame = tk.Frame(parent, bg=BG_COLOR)
    frame.pack(fill="x", pady=(2, 0))

    lbl = tk.Label(frame, text=label, bg=BG_COLOR, font=(DEFAULT_FONT, 9))
    lbl.pack(side="left")

    slider = ttk.Scale(frame, from_=from_, to=to, orient="horizontal",
                       style="Blue.Horizontal.TScale", command=command)
    slider.set(init)
    slider.pack(side="left", fill="x", expand=True, padx=5)

    # Editable entry for precise/out-of-range values
    val_var = tk.StringVar(value=f"{init}{suffix}")
    entry = tk.Entry(frame, textvariable=val_var, width=5, font=(DEFAULT_FONT, 9, "bold"),
                     fg="#2196F3", bg="white", relief="solid", bd=1, justify="center")
    entry.pack(side="left")

    # When user edits the entry and presses Enter, update the slider
    def _on_entry_commit(event=None):
        text = val_var.get().strip().rstrip(suffix.strip()) if suffix else val_var.get().strip()
        try:
            v = int(text)
        except ValueError:
            return
        # Clamp slider to its range, but let the command handle the actual value
        slider.set(max(from_, min(to, v)))
        # Fire the command with the typed value (may be outside slider range)
        command(str(v))

    entry.bind("<Return>", _on_entry_commit)
    entry.bind("<FocusOut>", _on_entry_commit)

    if tooltip:
        from spire_painter.tooltip import Tooltip
        Tooltip(lbl, tooltip)
        Tooltip(slider, tooltip)
        Tooltip(entry, tooltip)

    return slider, entry, val_var


def add_checkbox(parent, text, variable, command, tooltip=None):
    """Create a styled checkbox. Returns the Checkbutton widget."""
    chk = tk.Checkbutton(parent, text=text, font=(DEFAULT_FONT, 9),
                         variable=variable, bg=BG_COLOR, command=command)
    chk.pack(fill="x", pady=(2, 0))
    if tooltip:
        from spire_painter.tooltip import Tooltip
        Tooltip(chk, tooltip)
    return chk


def add_float_slider(parent, label, from_, to, init, command, resolution=0.5, suffix="", tooltip=None):
    """Create a labeled slider for float values with an editable entry.

    Returns (slider, entry, val_var).
    """
    from tkinter import ttk

    frame = tk.Frame(parent, bg=BG_COLOR)
    frame.pack(fill="x", pady=(2, 0))

    lbl = tk.Label(frame, text=label, bg=BG_COLOR, font=(DEFAULT_FONT, 9))
    lbl.pack(side="left")

    slider = ttk.Scale(frame, from_=from_, to=to, orient="horizontal",
                       style="Blue.Horizontal.TScale", command=command)
    slider.set(init)
    slider.pack(side="left", fill="x", expand=True, padx=5)

    val_var = tk.StringVar(value=f"{init}{suffix}")
    entry = tk.Entry(frame, textvariable=val_var, width=5, font=(DEFAULT_FONT, 9, "bold"),
                     fg="#2196F3", bg="white", relief="solid", bd=1, justify="center")
    entry.pack(side="left")

    def _on_entry_commit(event=None):
        text = val_var.get().strip().rstrip(suffix.strip()) if suffix else val_var.get().strip()
        try:
            v = float(text)
        except ValueError:
            return
        slider.set(max(from_, min(to, v)))
        command(str(v))

    entry.bind("<Return>", _on_entry_commit)
    entry.bind("<FocusOut>", _on_entry_commit)

    if tooltip:
        from spire_painter.tooltip import Tooltip
        Tooltip(lbl, tooltip)
        Tooltip(slider, tooltip)
        Tooltip(entry, tooltip)

    return slider, entry, val_var


def snap_slider(slider, entry, val_var, val, suffix=""):
    """Snap slider to integer, update entry display. Returns True if value changed."""
    v = round(float(val))
    if abs(float(val) - v) > 0.001:
        slider.set(v)
    new_text = f"{v}{suffix}"
    if val_var.get() != new_text:
        val_var.set(new_text)
        return True
    return False


def snap_float_slider(slider, entry, val_var, val, resolution=0.5, suffix=""):
    """Snap slider to resolution step, update entry display. Returns True if value changed."""
    v = round(float(val) / resolution) * resolution
    if abs(float(val) - v) > 0.001:
        slider.set(v)
    new_text = f"{v:.1f}{suffix}"
    if val_var.get() != new_text:
        val_var.set(new_text)
        return True
    return False
