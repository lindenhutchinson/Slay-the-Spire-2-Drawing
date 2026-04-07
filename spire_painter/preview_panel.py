import logging
import os
import time
import tkinter as tk
from PIL import Image, ImageTk

from spire_painter.constants import (
    DEFAULT_FONT, TEXT_COLOR, MIN_ZOOM, MAX_ZOOM, MAX_PREVIEW_DIM,
    ZOOM_IN_FACTOR, ZOOM_OUT_FACTOR, PREVIEW_FIT_SCALE, MIN_SELECTION_SIZE,
)

logger = logging.getLogger(__name__)


class PreviewPanel:
    """Zoomable, draggable line art preview canvas with inline crop support."""

    HANDLE_SIZE = 8
    HANDLE_HALF = 4

    def __init__(self, parent, on_image_loaded=None):
        """
        Args:
            parent: Parent tk frame to pack into.
            on_image_loaded: Optional callback() called when an image is successfully loaded.
        """
        self.on_image_loaded = on_image_loaded
        self._crop_callback = None
        self._on_crop_enter = None
        self._on_crop_exit = None

        tk.Label(parent, text="Live Line Art Preview",
                 font=(DEFAULT_FONT, 12, "bold"), bg="white", fg=TEXT_COLOR).pack(pady=10)

        self.canvas = tk.Canvas(parent, bg="#FAFAFA", highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Motion>", self._on_motion)

        self._tk_image = None
        self._base_img = None
        self._img_id = None
        self._hint_id = None
        self._zoom = 1.0
        self._drag_x = 0
        self._drag_y = 0
        self._last_cw = None
        self._last_ch = None

        # Crop mode state
        self._crop_mode = False
        self._crop_phase = None  # "adjusting" only now
        self._crop_rect_id = None
        self._crop_handle_ids = []
        self._crop_btn_frame = None
        self._crop_start_x = 0
        self._crop_start_y = 0
        self._crop_rx = 0
        self._crop_ry = 0
        self._crop_rw = 0
        self._crop_rh = 0
        self._crop_drag_action = None
        self._crop_drag_ox = 0
        self._crop_drag_oy = 0
        self._crop_dim_id = None
        self._pre_crop_img = None  # lineart image saved before crop
        self._crop_source_img = None  # original source image for cropping

        # Side-by-side mode
        self._side_by_side = False
        self._original_img = None  # original source image for comparison

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

            if self._base_img.width <= 0 or self._base_img.height <= 0:
                return

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
            logger.warning("Preview load failed: %s", e)

    def update_from_image(self, pil_img):
        """Update the preview from a PIL Image directly (no file load)."""
        if pil_img is None:
            return
        try:
            self._base_img = pil_img.convert("RGB") if pil_img.mode != "RGB" else pil_img

            if self._base_img.width <= 0 or self._base_img.height <= 0:
                return

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
            logger.warning("Preview update failed: %s", e)

    # ==================================================================
    # Side-by-side mode
    # ==================================================================

    def set_original_image(self, pil_img):
        """Store original image for side-by-side display."""
        self._original_img = pil_img.convert("RGB") if pil_img else None

    def toggle_side_by_side(self):
        """Toggle between normal and side-by-side preview mode."""
        self._side_by_side = not self._side_by_side
        self._redraw()

    # ==================================================================
    # Crop mode — inline selection on the preview canvas
    # ==================================================================

    def enter_crop_mode(self, callback, source_image, on_enter=None, on_exit=None):
        """Enter crop mode showing the original source image.

        Args:
            callback: callback(cropped_pil_image) called on confirm.
            source_image: PIL Image of the original source to display and crop from.
            on_enter: Optional callback() when crop mode starts (e.g. hide toolbar).
            on_exit: Optional callback() when crop mode ends (e.g. show toolbar).
        """
        if source_image is None:
            return
        self._crop_callback = callback
        self._on_crop_enter = on_enter
        self._on_crop_exit = on_exit
        self._crop_source_img = source_image.convert("RGB") if source_image.mode != "RGB" else source_image

        # Save current lineart image to restore on cancel
        self._pre_crop_img = self._base_img

        # Display the source image
        self._base_img = self._crop_source_img

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

        self._crop_mode = True
        self._crop_phase = "adjusting"
        self.canvas.config(cursor="crosshair")

        # Notify caller to hide toolbar
        if self._on_crop_enter:
            self._on_crop_enter()

        # Set initial crop rect to cover the full image
        img_coords = self.canvas.coords(self._img_id)
        img_cx, img_cy = img_coords[0], img_coords[1]
        disp_w = self._base_img.width * self._zoom
        disp_h = self._base_img.height * self._zoom
        self._crop_rx = img_cx - disp_w / 2
        self._crop_ry = img_cy - disp_h / 2
        self._crop_rw = disp_w
        self._crop_rh = disp_h

        # Draw crop rect and handles
        self._crop_rect_id = self.canvas.create_rectangle(
            self._crop_rx, self._crop_ry,
            self._crop_rx + self._crop_rw, self._crop_ry + self._crop_rh,
            outline="#FF4444", width=2, dash=(4, 4), tags=("crop_overlay", "crop_rect")
        )
        self._crop_draw_handles()
        self._crop_show_buttons()

        self.canvas.focus_set()
        self.canvas.bind("<Escape>", self._crop_cancel)
        self.canvas.bind("<Return>", lambda e: self._crop_confirm())

    def _exit_crop_mode(self):
        """Clean up all crop UI and restore normal preview mode."""
        self._crop_mode = False
        self._crop_phase = None
        self._crop_drag_action = None
        self.canvas.config(cursor="fleur")
        self.canvas.delete("crop_overlay")
        self.canvas.delete("crop_rect")
        self.canvas.delete("crop_handle")
        self._crop_rect_id = None
        self._crop_handle_ids.clear()
        if self._crop_btn_frame:
            self._crop_btn_frame.destroy()
            self._crop_btn_frame = None
        self.canvas.delete("crop_btn_window")
        self.canvas.unbind("<Escape>")
        self.canvas.unbind("<Return>")
        self._crop_source_img = None

        # Notify caller to show toolbar again
        if self._on_crop_exit:
            self._on_crop_exit()

    # ------------------------------------------------------------------
    # Mouse dispatch — routes to crop or normal pan
    # ------------------------------------------------------------------

    def _on_press(self, event):
        if self._crop_mode:
            self._crop_on_press(event)
        else:
            self._drag_x = event.x
            self._drag_y = event.y

    def _on_drag(self, event):
        if self._crop_mode:
            self._crop_on_drag(event)
        else:
            self._pan_motion(event)

    def _on_release(self, event):
        if self._crop_mode:
            self._crop_on_release(event)

    def _on_motion(self, event):
        if self._crop_mode and self._crop_phase == "adjusting" and not self._crop_drag_action:
            action = self._crop_hit_test(event.x, event.y)
            cursor_map = {
                "nw": "top_left_corner", "ne": "top_right_corner",
                "sw": "bottom_left_corner", "se": "bottom_right_corner",
                "n": "top_side", "s": "bottom_side",
                "e": "right_side", "w": "left_side",
                "move": "fleur",
            }
            self.canvas.config(cursor=cursor_map.get(action, "crosshair"))

    # ------------------------------------------------------------------
    # Normal pan
    # ------------------------------------------------------------------

    def _pan_motion(self, event):
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y

        if self._img_id:
            self.canvas.move(self._img_id, dx, dy)
        if self._hint_id:
            self.canvas.move(self._hint_id, dx, dy)

        self._drag_x = event.x
        self._drag_y = event.y

    # ------------------------------------------------------------------
    # Crop mouse handling (adjusting only — no drawing phase)
    # ------------------------------------------------------------------

    def _crop_on_press(self, event):
        if self._crop_phase == "adjusting":
            self._crop_start_adjust(event)

    def _crop_on_drag(self, event):
        if self._crop_phase == "adjusting" and self._crop_drag_action:
            self._crop_do_adjust(event)

    def _crop_on_release(self, event):
        if self._crop_phase == "adjusting":
            self._crop_drag_action = None

    # ------------------------------------------------------------------
    # Crop adjusting phase
    # ------------------------------------------------------------------

    def _get_image_canvas_bounds(self):
        """Return (left, top, right, bottom) of the displayed image in canvas coords."""
        if not self._img_id or not self._base_img:
            return 0, 0, 0, 0
        img_coords = self.canvas.coords(self._img_id)
        img_cx, img_cy = img_coords[0], img_coords[1]
        disp_w = self._base_img.width * self._zoom
        disp_h = self._base_img.height * self._zoom
        return img_cx - disp_w / 2, img_cy - disp_h / 2, img_cx + disp_w / 2, img_cy + disp_h / 2

    def _clamp_crop_to_image(self):
        """Constrain the crop rectangle to stay within the displayed image bounds."""
        il, it, ir, ib = self._get_image_canvas_bounds()
        img_w = ir - il
        img_h = ib - it

        # Clamp size to image
        self._crop_rw = min(self._crop_rw, img_w)
        self._crop_rh = min(self._crop_rh, img_h)

        # Clamp position
        self._crop_rx = max(il, min(self._crop_rx, ir - self._crop_rw))
        self._crop_ry = max(it, min(self._crop_ry, ib - self._crop_rh))

    def _crop_update_rect(self):
        if self._crop_rect_id:
            self.canvas.coords(self._crop_rect_id,
                               self._crop_rx, self._crop_ry,
                               self._crop_rx + self._crop_rw,
                               self._crop_ry + self._crop_rh)
        self._crop_draw_handles()

    def _crop_draw_handles(self):
        self.canvas.delete("crop_handle")
        self._crop_handle_ids.clear()
        h = self.HANDLE_HALF
        # Corners + edge midpoints
        mx = self._crop_rx + self._crop_rw / 2
        my = self._crop_ry + self._crop_rh / 2
        points = [
            (self._crop_rx, self._crop_ry),
            (self._crop_rx + self._crop_rw, self._crop_ry),
            (self._crop_rx, self._crop_ry + self._crop_rh),
            (self._crop_rx + self._crop_rw, self._crop_ry + self._crop_rh),
            (mx, self._crop_ry),       # n
            (mx, self._crop_ry + self._crop_rh),  # s
            (self._crop_rx, my),        # w
            (self._crop_rx + self._crop_rw, my),   # e
        ]
        for cx, cy in points:
            hid = self.canvas.create_rectangle(
                cx - h, cy - h, cx + h, cy + h,
                fill="#FFFFFF", outline="#FF4444", width=1,
                tags=("crop_overlay", "crop_handle")
            )
            self._crop_handle_ids.append(hid)

    def _crop_hit_test(self, ex, ey):
        margin = self.HANDLE_SIZE + 4
        rx, ry, rw, rh = self._crop_rx, self._crop_ry, self._crop_rw, self._crop_rh
        mx = rx + rw / 2
        my = ry + rh / 2

        # Check corners first
        corners = {
            "nw": (rx, ry), "ne": (rx + rw, ry),
            "sw": (rx, ry + rh), "se": (rx + rw, ry + rh),
        }
        for tag, (cx, cy) in corners.items():
            if abs(ex - cx) <= margin and abs(ey - cy) <= margin:
                return tag

        # Check edge midpoints
        edges = {
            "n": (mx, ry), "s": (mx, ry + rh),
            "w": (rx, my), "e": (rx + rw, my),
        }
        for tag, (cx, cy) in edges.items():
            if abs(ex - cx) <= margin and abs(ey - cy) <= margin:
                return tag

        # Check inside rect for move
        if rx <= ex <= rx + rw and ry <= ey <= ry + rh:
            return "move"
        return None

    def _crop_start_adjust(self, event):
        action = self._crop_hit_test(event.x, event.y)
        if not action:
            return
        if action == "move":
            self._crop_drag_action = "move"
            self._crop_drag_ox = event.x - self._crop_rx
            self._crop_drag_oy = event.y - self._crop_ry
        else:
            self._crop_drag_action = action

    def _crop_do_adjust(self, event):
        ex, ey = event.x, event.y
        act = self._crop_drag_action

        if act == "move":
            self._crop_rx = ex - self._crop_drag_ox
            self._crop_ry = ey - self._crop_drag_oy
        elif act == "nw":
            new_rw = (self._crop_rx + self._crop_rw) - ex
            new_rh = (self._crop_ry + self._crop_rh) - ey
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self._crop_rx = ex
                self._crop_ry = ey
                self._crop_rw = new_rw
                self._crop_rh = new_rh
        elif act == "ne":
            new_rw = ex - self._crop_rx
            new_rh = (self._crop_ry + self._crop_rh) - ey
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self._crop_ry = ey
                self._crop_rw = new_rw
                self._crop_rh = new_rh
        elif act == "sw":
            new_rw = (self._crop_rx + self._crop_rw) - ex
            new_rh = ey - self._crop_ry
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self._crop_rx = ex
                self._crop_rw = new_rw
                self._crop_rh = new_rh
        elif act == "se":
            new_rw = ex - self._crop_rx
            new_rh = ey - self._crop_ry
            if new_rw > MIN_SELECTION_SIZE:
                self._crop_rw = new_rw
            if new_rh > MIN_SELECTION_SIZE:
                self._crop_rh = new_rh
        elif act == "n":
            new_rh = (self._crop_ry + self._crop_rh) - ey
            if new_rh > MIN_SELECTION_SIZE:
                self._crop_ry = ey
                self._crop_rh = new_rh
        elif act == "s":
            new_rh = ey - self._crop_ry
            if new_rh > MIN_SELECTION_SIZE:
                self._crop_rh = new_rh
        elif act == "w":
            new_rw = (self._crop_rx + self._crop_rw) - ex
            if new_rw > MIN_SELECTION_SIZE:
                self._crop_rx = ex
                self._crop_rw = new_rw
        elif act == "e":
            new_rw = ex - self._crop_rx
            if new_rw > MIN_SELECTION_SIZE:
                self._crop_rw = new_rw

        self._clamp_crop_to_image()
        self._crop_update_rect()
        self._crop_update_button_pos()

    # ------------------------------------------------------------------
    # Crop confirm / cancel buttons
    # ------------------------------------------------------------------

    def _crop_show_buttons(self):
        self._crop_btn_frame = tk.Frame(self.canvas, bg="")
        btn_confirm = tk.Button(
            self._crop_btn_frame, text="✓", font=(DEFAULT_FONT, 14, "bold"),
            bg="#4CAF50", fg="white", relief="flat", padx=8, pady=2,
            activebackground="#388E3C", activeforeground="white",
            command=self._crop_confirm, cursor="hand2", width=2
        )
        btn_confirm.pack(side="left", padx=(0, 4))

        btn_cancel = tk.Button(
            self._crop_btn_frame, text="✕", font=(DEFAULT_FONT, 14),
            bg="#E53935", fg="white", relief="flat", padx=8, pady=2,
            activebackground="#C62828", activeforeground="white",
            command=self._crop_cancel, cursor="hand2", width=2
        )
        btn_cancel.pack(side="left")

        self._crop_update_button_pos()

    def _crop_update_button_pos(self):
        if not self._crop_btn_frame:
            return
        cx = self._crop_rx + self._crop_rw / 2
        cy = self._crop_ry + self._crop_rh + 12
        self.canvas.delete("crop_btn_window")
        self.canvas.create_window(cx, cy, window=self._crop_btn_frame,
                                  anchor="n", tags=("crop_overlay", "crop_btn_window"))

    def _crop_hide_buttons(self):
        if self._crop_btn_frame:
            self._crop_btn_frame.destroy()
            self._crop_btn_frame = None
        self.canvas.delete("crop_btn_window")

    # ------------------------------------------------------------------
    # Crop actions
    # ------------------------------------------------------------------

    def _crop_confirm(self, event=None):
        if self._crop_rw <= MIN_SELECTION_SIZE or self._crop_rh <= MIN_SELECTION_SIZE:
            return
        if not self._crop_source_img or not self._img_id:
            self._exit_crop_mode()
            return

        # Convert canvas selection coords to source image pixel coords
        il, it, ir, ib = self._get_image_canvas_bounds()

        if self._zoom <= 0:
            self._exit_crop_mode()
            return

        px_x = (self._crop_rx - il) / self._zoom
        px_y = (self._crop_ry - it) / self._zoom
        px_w = self._crop_rw / self._zoom
        px_h = self._crop_rh / self._zoom

        x1 = max(0, int(px_x))
        y1 = max(0, int(px_y))
        x2 = min(self._crop_source_img.width, int(px_x + px_w))
        y2 = min(self._crop_source_img.height, int(px_y + px_h))

        if x2 - x1 < 1 or y2 - y1 < 1:
            self._exit_crop_mode()
            return

        cropped = self._crop_source_img.crop((x1, y1, x2, y2))

        # Restore lineart image before exiting
        self._base_img = self._pre_crop_img
        self._pre_crop_img = None
        cb = self._crop_callback

        self._exit_crop_mode()

        if cb:
            cb(cropped)

    def _crop_cancel(self, event=None):
        # Restore lineart image
        if self._pre_crop_img is not None:
            self._base_img = self._pre_crop_img
            self._pre_crop_img = None
            self._redraw()
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if self._img_id:
                self.canvas.coords(self._img_id, cw // 2, ch // 2)
        self._exit_crop_mode()

    # ==================================================================
    # Internal rendering
    # ==================================================================

    def _redraw(self):
        if not self._base_img:
            return

        display_img = self._base_img

        # Side-by-side: composite original (left) and lineart (right)
        if self._side_by_side and self._original_img and not self._crop_mode:
            orig = self._original_img
            line = self._base_img

            # Match heights
            target_h = min(orig.height, line.height)
            if target_h <= 0:
                target_h = max(orig.height, line.height)
            if target_h <= 0:
                return

            orig_w = max(1, int(orig.width * target_h / orig.height))
            line_w = max(1, int(line.width * target_h / line.height))

            resample = Image.Resampling.LANCZOS
            left = orig.resize((orig_w, target_h), resample)
            right = line.resize((line_w, target_h), resample)

            separator = 4
            composite = Image.new("RGB", (orig_w + line_w + separator, target_h), (200, 200, 200))
            composite.paste(left, (0, 0))
            composite.paste(right, (orig_w + separator, 0))
            display_img = composite

        new_w = int(display_img.width * self._zoom)
        new_h = int(display_img.height * self._zoom)

        if new_w <= 0 or new_h <= 0 or new_w > MAX_PREVIEW_DIM or new_h > MAX_PREVIEW_DIM:
            return

        resample = Image.Resampling.LANCZOS if self._zoom < 1.0 else Image.Resampling.NEAREST
        resized = display_img.resize((new_w, new_h), resample)

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

    def _on_zoom(self, event):
        if not self._base_img or self._crop_mode:
            return

        if event.delta > 0:
            self._zoom *= ZOOM_IN_FACTOR
        elif event.delta < 0:
            self._zoom *= ZOOM_OUT_FACTOR

        self._zoom = max(MIN_ZOOM, min(self._zoom, MAX_ZOOM))
        self._redraw()
