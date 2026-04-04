import os
import time
import tkinter as tk
from PIL import Image, ImageTk

from spire_painter.constants import (
    DEFAULT_FONT, TEXT_COLOR, MIN_ZOOM, MAX_ZOOM, MAX_PREVIEW_DIM,
    ZOOM_IN_FACTOR, ZOOM_OUT_FACTOR, PREVIEW_FIT_SCALE, MIN_SELECTION_SIZE,
)


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

        tk.Label(parent, text="Live Line Art Preview",
                 font=(DEFAULT_FONT, 12, "bold"), bg="white", fg=TEXT_COLOR).pack(pady=10)

        self.canvas = tk.Canvas(parent, bg="#FAFAFA", highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
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

        # Crop mode state
        self._crop_mode = False
        self._crop_phase = None  # "drawing" or "adjusting"
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

    def update_from_image(self, pil_img):
        """Update the preview from a PIL Image directly (no file load)."""
        if pil_img is None:
            return
        try:
            self._base_img = pil_img.convert("RGB") if pil_img.mode != "RGB" else pil_img

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
            print(f"Preview update failed: {e}")

    # ==================================================================
    # Crop mode — inline selection on the preview canvas
    # ==================================================================

    def enter_crop_mode(self, callback):
        """Enter crop mode. callback(cropped_path) is called on confirm."""
        if not self._base_img:
            return
        self._crop_callback = callback
        self._crop_mode = True
        self._crop_phase = "drawing"
        self.canvas.config(cursor="crosshair")

        # Dim overlay
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        self._crop_dim_id = self.canvas.create_rectangle(
            0, 0, cw, ch, fill="black", stipple="gray50", tags="crop_overlay"
        )
        if self._img_id:
            self.canvas.tag_raise(self._img_id)

        self._crop_hint_id = self.canvas.create_text(
            cw // 2, 30,
            text="Drag to select crop area  |  Esc to cancel",
            fill="white", font=(DEFAULT_FONT, 11, "bold"), tags="crop_overlay"
        )

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
    # Crop drawing phase
    # ------------------------------------------------------------------

    def _crop_on_press(self, event):
        if self._crop_phase == "drawing":
            self._crop_start_x = event.x
            self._crop_start_y = event.y
            if self._crop_rect_id:
                self.canvas.delete("crop_rect")
                self.canvas.delete("crop_handle")
                self._crop_handle_ids.clear()
            self._crop_rect_id = self.canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline="#FF4444", width=2, dash=(4, 4), tags=("crop_overlay", "crop_rect")
            )
        elif self._crop_phase == "adjusting":
            self._crop_start_adjust(event)

    def _crop_on_drag(self, event):
        if self._crop_phase == "drawing" and self._crop_rect_id:
            self.canvas.coords(self._crop_rect_id,
                               self._crop_start_x, self._crop_start_y,
                               event.x, event.y)
        elif self._crop_phase == "adjusting" and self._crop_drag_action:
            self._crop_do_adjust(event)

    def _crop_on_release(self, event):
        if self._crop_phase == "drawing":
            self._crop_finish_drawing(event)
        elif self._crop_phase == "adjusting":
            self._crop_drag_action = None
            self.canvas.config(cursor="crosshair")

    def _crop_finish_drawing(self, event):
        x1, y1 = self._crop_start_x, self._crop_start_y
        x2, y2 = event.x, event.y
        self._crop_rx = min(x1, x2)
        self._crop_ry = min(y1, y2)
        self._crop_rw = abs(x2 - x1)
        self._crop_rh = abs(y2 - y1)

        if self._crop_rw <= MIN_SELECTION_SIZE or self._crop_rh <= MIN_SELECTION_SIZE:
            return

        self._crop_phase = "adjusting"
        self._crop_update_rect()
        self._crop_draw_handles()
        self._crop_show_buttons()

    # ------------------------------------------------------------------
    # Crop adjusting phase
    # ------------------------------------------------------------------

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
        corners = [
            (self._crop_rx, self._crop_ry),
            (self._crop_rx + self._crop_rw, self._crop_ry),
            (self._crop_rx, self._crop_ry + self._crop_rh),
            (self._crop_rx + self._crop_rw, self._crop_ry + self._crop_rh),
        ]
        for cx, cy in corners:
            hid = self.canvas.create_rectangle(
                cx - h, cy - h, cx + h, cy + h,
                fill="#FFFFFF", outline="#FF4444", width=1,
                tags=("crop_overlay", "crop_handle")
            )
            self._crop_handle_ids.append(hid)

    def _crop_hit_test(self, ex, ey):
        margin = self.HANDLE_SIZE + 4
        corners = {
            "nw": (self._crop_rx, self._crop_ry),
            "ne": (self._crop_rx + self._crop_rw, self._crop_ry),
            "sw": (self._crop_rx, self._crop_ry + self._crop_rh),
            "se": (self._crop_rx + self._crop_rw, self._crop_ry + self._crop_rh),
        }
        for tag, (cx, cy) in corners.items():
            if abs(ex - cx) <= margin and abs(ey - cy) <= margin:
                return tag
        if (self._crop_rx <= ex <= self._crop_rx + self._crop_rw and
                self._crop_ry <= ey <= self._crop_ry + self._crop_rh):
            return "move"
        return None

    def _crop_start_adjust(self, event):
        action = self._crop_hit_test(event.x, event.y)
        if action == "move":
            self._crop_drag_action = "move"
            self._crop_drag_ox = event.x - self._crop_rx
            self._crop_drag_oy = event.y - self._crop_ry
            self.canvas.config(cursor="fleur")
        elif action in ("nw", "ne", "sw", "se"):
            self._crop_drag_action = action
            cursor_map = {"nw": "top_left_corner", "ne": "top_right_corner",
                          "sw": "bottom_left_corner", "se": "bottom_right_corner"}
            self.canvas.config(cursor=cursor_map[action])
        else:
            # Clicked outside selection — restart drawing
            self._crop_phase = "drawing"
            self.canvas.delete("crop_rect")
            self.canvas.delete("crop_handle")
            self._crop_handle_ids.clear()
            self._crop_rect_id = None
            self._crop_hide_buttons()
            self._crop_on_press(event)

    def _crop_do_adjust(self, event):
        ex, ey = event.x, event.y
        if self._crop_drag_action == "move":
            self._crop_rx = ex - self._crop_drag_ox
            self._crop_ry = ey - self._crop_drag_oy
        elif self._crop_drag_action == "nw":
            new_rw = (self._crop_rx + self._crop_rw) - ex
            new_rh = (self._crop_ry + self._crop_rh) - ey
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self._crop_rx = ex
                self._crop_ry = ey
                self._crop_rw = new_rw
                self._crop_rh = new_rh
        elif self._crop_drag_action == "ne":
            new_rw = ex - self._crop_rx
            new_rh = (self._crop_ry + self._crop_rh) - ey
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self._crop_ry = ey
                self._crop_rw = new_rw
                self._crop_rh = new_rh
        elif self._crop_drag_action == "sw":
            new_rw = (self._crop_rx + self._crop_rw) - ex
            new_rh = ey - self._crop_ry
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self._crop_rx = ex
                self._crop_rw = new_rw
                self._crop_rh = new_rh
        elif self._crop_drag_action == "se":
            new_rw = ex - self._crop_rx
            new_rh = ey - self._crop_ry
            if new_rw > MIN_SELECTION_SIZE:
                self._crop_rw = new_rw
            if new_rh > MIN_SELECTION_SIZE:
                self._crop_rh = new_rh

        self._crop_update_rect()
        self._crop_update_button_pos()

    # ------------------------------------------------------------------
    # Crop confirm / cancel buttons
    # ------------------------------------------------------------------

    def _crop_show_buttons(self):
        self._crop_btn_frame = tk.Frame(self.canvas, bg="")
        btn_confirm = tk.Button(
            self._crop_btn_frame, text="✓ Crop", font=(DEFAULT_FONT, 10, "bold"),
            bg="#4CAF50", fg="white", relief="flat", padx=16, pady=4,
            activebackground="#388E3C", activeforeground="white",
            command=self._crop_confirm, cursor="hand2"
        )
        btn_confirm.pack(side="left", padx=(0, 8))

        btn_cancel = tk.Button(
            self._crop_btn_frame, text="✕ Cancel", font=(DEFAULT_FONT, 10),
            bg="#666666", fg="white", relief="flat", padx=12, pady=4,
            activebackground="#444444", activeforeground="white",
            command=self._crop_cancel, cursor="hand2"
        )
        btn_cancel.pack(side="left")

        self._crop_update_button_pos()

    def _crop_update_button_pos(self):
        if not self._crop_btn_frame:
            return
        cx = self._crop_rx + self._crop_rw // 2
        cy = self._crop_ry + self._crop_rh + 20
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
        if not self._base_img or not self._img_id:
            self._exit_crop_mode()
            return

        # Convert canvas selection coords to image pixel coords
        # The image is displayed centered at some canvas position with self._zoom scale
        img_coords = self.canvas.coords(self._img_id)  # center x, y
        img_cx, img_cy = img_coords[0], img_coords[1]
        disp_w = self._base_img.width * self._zoom
        disp_h = self._base_img.height * self._zoom
        img_left = img_cx - disp_w / 2
        img_top = img_cy - disp_h / 2

        # Selection rect in canvas coords -> image pixel coords
        px_x = (self._crop_rx - img_left) / self._zoom
        px_y = (self._crop_ry - img_top) / self._zoom
        px_w = self._crop_rw / self._zoom
        px_h = self._crop_rh / self._zoom

        # Clamp to image bounds
        x1 = max(0, int(px_x))
        y1 = max(0, int(px_y))
        x2 = min(self._base_img.width, int(px_x + px_w))
        y2 = min(self._base_img.height, int(px_y + px_h))

        if x2 - x1 < 1 or y2 - y1 < 1:
            self._exit_crop_mode()
            return

        cropped = self._base_img.crop((x1, y1, x2, y2))

        self._exit_crop_mode()

        if self._crop_callback:
            self._crop_callback(cropped)

    def _crop_cancel(self, event=None):
        self._exit_crop_mode()

    # ==================================================================
    # Internal rendering
    # ==================================================================

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

    def _on_zoom(self, event):
        if not self._base_img or self._crop_mode:
            return

        if event.delta > 0:
            self._zoom *= ZOOM_IN_FACTOR
        elif event.delta < 0:
            self._zoom *= ZOOM_OUT_FACTOR

        self._zoom = max(MIN_ZOOM, min(self._zoom, MAX_ZOOM))
        self._redraw()
