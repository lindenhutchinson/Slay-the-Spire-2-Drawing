import tkinter as tk
from tkinter import ttk

from spire_painter.constants import DEFAULT_FONT, BG_COLOR
from spire_painter.tooltip import Tooltip
from spire_painter.ui.helpers import add_slider


DRAW_MODE_MAP = {"Right Click (StS2)": "right", "Left Click (Paint)": "left"}
DRAW_MODE_REVERSE = {v: k for k, v in DRAW_MODE_MAP.items()}


class DrawingSettingsPanel:
    """Draw mode, speed, brush width, and edge close controls."""

    def __init__(self, parent, config, on_speed_change, on_brush_change,
                 on_edge_close_change, on_draw_mode_change):
        frame = ttk.LabelFrame(parent, text=" Drawing Settings ", padding=(10, 5))
        frame.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 5))
        wrap = tk.Frame(frame, bg=BG_COLOR)
        wrap.pack(expand=True, fill="x")

        # Draw mode
        click_frame = tk.Frame(wrap, bg=BG_COLOR)
        click_frame.pack(fill="x", pady=(0, 5))
        lbl = tk.Label(click_frame, text="Draw Button:", bg=BG_COLOR, font=(DEFAULT_FONT, 9))
        lbl.pack(side="left")
        self.draw_mode_combo = ttk.Combobox(click_frame, values=list(DRAW_MODE_MAP.keys()),
                                            state="readonly", width=18, font=(DEFAULT_FONT, 9))
        self.draw_mode_combo.set(DRAW_MODE_REVERSE.get(config.draw_mode, "Right Click (StS2)"))
        self.draw_mode_combo.pack(side="left", padx=(10, 0))
        self.draw_mode_combo.bind("<<ComboboxSelected>>", lambda e: on_draw_mode_change())
        Tooltip(lbl, "Which mouse button to simulate when drawing.")
        Tooltip(self.draw_mode_combo, "Right = draw in StS2, Left = draw in Paint.")

        # Sliders
        self.speed_slider, self.speed_entry, self.speed_var = add_slider(
            wrap, "Draw Speed:", 1, 20, config.speed, on_speed_change,
            tooltip="Contour points to skip. Lower = smoother but slower. 2-4 recommended.")
        self.brush_slider, self.brush_entry, self.brush_var = add_slider(
            wrap, "Brush Width:", 1, 15, config.brush_width, on_brush_change, suffix=" px",
            tooltip="In-game pen thickness (pixels). Affects preview accuracy.")
        self.edge_close_slider, self.edge_close_entry, self.edge_close_var = add_slider(
            wrap, "Edge Close:", 1, 9, config.edge_close, on_edge_close_change,
            tooltip="Bridge gaps in edges. Higher = more connected lines. 1 = off.")

    @property
    def draw_mode(self):
        return DRAW_MODE_MAP.get(self.draw_mode_combo.get(), "right")
