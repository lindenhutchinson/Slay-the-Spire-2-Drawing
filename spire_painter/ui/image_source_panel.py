import tkinter as tk
from tkinter import ttk

from spire_painter.constants import DEFAULT_FONT, BG_COLOR
from spire_painter.ui.helpers import flat_button, add_slider


class ImageSourcePanel:
    """Detail/thickness sliders and image load buttons."""

    def __init__(self, parent, initial_detail, initial_thickness,
                 on_detail_change, on_thickness_change,
                 on_select_image, on_refresh, on_load_existing):
        frame = ttk.LabelFrame(parent, text=" Image Source ", padding=(10, 5))
        frame.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 2))
        wrap = tk.Frame(frame, bg=BG_COLOR)
        wrap.pack(expand=True, fill="x")

        self.detail_slider, self.lbl_detail_val = add_slider(
            wrap, "Detail:", 1, 10, initial_detail, on_detail_change,
            tooltip="How many edges to detect. Higher = more lines, finer detail.")
        self.thickness_slider, self.lbl_thick_val = add_slider(
            wrap, "Thickness:", 1, 7, initial_thickness, on_thickness_change,
            tooltip="Line thickness. 1 = thin single-pixel edges. Higher = bolder strokes.")

        btn_row = tk.Frame(wrap, bg=BG_COLOR)
        btn_row.pack(fill="x", pady=(5, 0))
        self.btn_image = flat_button(btn_row, "Select Image", on_select_image,
                                     bg="#E3F2FD", active_bg="#BBDEFB", fg="#0D47A1")
        self.btn_image.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_reprocess = flat_button(btn_row, "Refresh Line Art", on_refresh,
                                         state=tk.DISABLED, bg="#E3F2FD", active_bg="#BBDEFB", fg="#0D47A1")
        self.btn_reprocess.pack(side="left", fill="x", expand=True, padx=(3, 3))
        self.btn_load_existing = flat_button(btn_row, "Open Saved", on_load_existing,
                                             bg="#F3E5F5", active_bg="#E1BEE7", fg="#4A148C")
        self.btn_load_existing.pack(side="left", fill="x", expand=True, padx=(3, 0))
