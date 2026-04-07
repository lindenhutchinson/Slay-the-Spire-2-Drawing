import tkinter as tk
from tkinter import ttk

from spire_painter.constants import DEFAULT_FONT, BG_COLOR
from spire_painter.ui.helpers import flat_button, add_slider, add_float_slider, add_checkbox


class ImageSourcePanel:
    """Detail/thickness/blur/min-contour/CLAHE sliders, simplify toggle, and image load buttons."""

    def __init__(self, parent, config,
                 on_detail_change, on_thickness_change,
                 on_blur_change, on_min_contour_change,
                 on_clahe_change,
                 on_select_image, on_refresh, on_load_existing, on_optimize,
                 on_bg_removal_toggle):
        frame = ttk.LabelFrame(parent, text=" Image Source ", padding=(10, 5))
        frame.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 2))
        wrap = tk.Frame(frame, bg=BG_COLOR)
        wrap.pack(expand=True, fill="x")

        self.detail_slider, self.detail_entry, self.detail_var = add_slider(
            wrap, "Detail:", 1, 10, config.detail, on_detail_change,
            tooltip="Edge detection sensitivity. Higher = more lines, finer detail.")
        self.thickness_slider, self.thickness_entry, self.thickness_var = add_slider(
            wrap, "Thickness:", 1, 7, config.thickness, on_thickness_change,
            tooltip="Line thickness. 1 = thin single-pixel edges. Higher = bolder strokes.")
        self.blur_slider, self.blur_entry, self.blur_var = add_slider(
            wrap, "Smoothing:", 1, 21, config.blur, on_blur_change,
            tooltip="Bilateral filter strength. Preserves edges while removing noise. Higher = smoother.")
        self.min_contour_slider, self.min_contour_entry, self.min_contour_var = add_slider(
            wrap, "Min Length:", 0, 50, config.min_contour_len, on_min_contour_change,
            tooltip="Minimum contour length in pixels. Filters out small noise/speckle dots. 0 = keep all.")
        self.clahe_slider, self.clahe_entry, self.clahe_var = add_float_slider(
            wrap, "Contrast:", 0, 8, config.clahe_clip, on_clahe_change,
            tooltip="CLAHE contrast enhancement. 0 = off. Higher = more contrast before edge detection. Helps with low-contrast images.")

        from spire_painter.tooltip import Tooltip
        self.bg_removal_var = tk.BooleanVar(value=config.bg_removal)
        self.chk_bg_removal = tk.Checkbutton(wrap, text="Flatten Background", font=(DEFAULT_FONT, 9),
                                             variable=self.bg_removal_var, bg=BG_COLOR,
                                             command=on_bg_removal_toggle)
        self.chk_bg_removal.pack(fill="x", pady=(2, 0))
        Tooltip(self.chk_bg_removal, "Detect the dominant color and flatten it to white before edge detection. Removes noise from backgrounds, gradients, and textures.")

        btn_row = tk.Frame(wrap, bg=BG_COLOR)
        btn_row.pack(fill="x", pady=(5, 0))
        self.btn_image = flat_button(btn_row, "Select Image", on_select_image,
                                     bg="#E3F2FD", active_bg="#BBDEFB", fg="#0D47A1")
        self.btn_image.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_reprocess = flat_button(btn_row, "Refresh", on_refresh,
                                         state=tk.DISABLED, bg="#E3F2FD", active_bg="#BBDEFB", fg="#0D47A1")
        self.btn_reprocess.pack(side="left", fill="x", expand=True, padx=(3, 3))
        self.btn_load_existing = flat_button(btn_row, "Open Saved", on_load_existing,
                                             bg="#F3E5F5", active_bg="#E1BEE7", fg="#4A148C")
        self.btn_load_existing.pack(side="left", fill="x", expand=True, padx=(3, 3))
        self.btn_optimize = flat_button(btn_row, "Optimize", on_optimize,
                                        state=tk.DISABLED, bg="#E8F5E9", active_bg="#C8E6C9", fg="#1B5E20")
        self.btn_optimize.pack(side="left", fill="x", expand=True, padx=(3, 0))
