import os
import tkinter as tk
from PIL import Image, ImageTk

from spire_painter.constants import (
    DEFAULT_FONT, TEXT_COLOR, MIN_ZOOM, MAX_ZOOM, MAX_PREVIEW_DIM,
    ZOOM_IN_FACTOR, ZOOM_OUT_FACTOR, PREVIEW_FIT_SCALE,
)


class PreviewPanel:
    """Zoomable, draggable line art preview canvas."""

    def __init__(self, parent, on_image_loaded=None):
        """
        Args:
            parent: Parent tk frame to pack into.
            on_image_loaded: Optional callback() called when an image is successfully loaded.
        """
        self.on_image_loaded = on_image_loaded

        tk.Label(parent, text="Live Line Art Preview",
                 font=(DEFAULT_FONT, 12, "bold"), bg="white", fg=TEXT_COLOR).pack(pady=10)

        self.canvas = tk.Canvas(parent, bg="#FAFAFA", highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.canvas.bind("<Configure>", self._on_resize)

        self._tk_image = None
        self._base_img = None
        self._img_id = None
        self._hint_id = None
        self._zoom = 1.0
        self._drag_x = 0
        self._drag_y = 0
        self._last_cw = None
        self._last_ch = None

    def show_hint(self):
        """Display the initial hint text (call after the canvas is realized)."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        self._last_cw = cw
        self._last_ch = ch
        self._hint_id = self.canvas.create_text(
            cw // 2, ch // 2,
            text="(No Preview)\nGenerate or select line art on the left\n\n"
                 "Tip: After generating, use scroll wheel to zoom and drag to pan",
            fill="gray", font=(DEFAULT_FONT, 11), justify="center"
        )

    def update(self, image_path):
        """Load an image file into the preview."""
        if not image_path or not os.path.exists(image_path):
            return

        try:
            self._base_img = Image.open(image_path).convert("RGB")

            if self._hint_id:
                self.canvas.delete(self._hint_id)
                self._hint_id = None

            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw <= 1:
                cw, ch = 500, 500

            scale_w = cw / self._base_img.width
            scale_h = ch / self._base_img.height
            self._zoom = min(scale_w, scale_h) * PREVIEW_FIT_SCALE

            self._redraw()

            if self._img_id:
                self.canvas.coords(self._img_id, cw // 2, ch // 2)

            if self.on_image_loaded:
                self.on_image_loaded()
        except Exception as e:
            print(f"Preview load failed: {e}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _redraw(self):
        if not self._base_img:
            return

        new_w = int(self._base_img.width * self._zoom)
        new_h = int(self._base_img.height * self._zoom)

        if new_w <= 0 or new_h <= 0 or new_w > MAX_PREVIEW_DIM or new_h > MAX_PREVIEW_DIM:
            return

        resample = Image.Resampling.LANCZOS if self._zoom < 1.0 else Image.Resampling.NEAREST
        resized = self._base_img.resize((new_w, new_h), resample)

        self._tk_image = ImageTk.PhotoImage(resized)

        if self._img_id:
            self.canvas.itemconfig(self._img_id, image=self._tk_image)
        else:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw <= 1:
                cw, ch = 500, 500
            self._img_id = self.canvas.create_image(
                cw // 2, ch // 2, image=self._tk_image, anchor="center"
            )

    def _on_resize(self, event):
        cw, ch = event.width, event.height
        if self._last_cw is not None and self._last_ch is not None:
            dx = (cw - self._last_cw) / 2
            dy = (ch - self._last_ch) / 2
            if self._img_id:
                self.canvas.move(self._img_id, dx, dy)
            if self._hint_id:
                self.canvas.move(self._hint_id, dx, dy)
        self._last_cw = cw
        self._last_ch = ch

    def _on_drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag_motion(self, event):
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y

        if self._img_id:
            self.canvas.move(self._img_id, dx, dy)
        if self._hint_id:
            self.canvas.move(self._hint_id, dx, dy)

        self._drag_x = event.x
        self._drag_y = event.y

    def _on_zoom(self, event):
        if not self._base_img:
            return

        if event.delta > 0:
            self._zoom *= ZOOM_IN_FACTOR
        elif event.delta < 0:
            self._zoom *= ZOOM_OUT_FACTOR

        self._zoom = max(MIN_ZOOM, min(self._zoom, MAX_ZOOM))
        self._redraw()
