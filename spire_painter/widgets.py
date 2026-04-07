import os
import time
import ctypes
import tkinter as tk
from PIL import Image, ImageTk, ImageGrab, ImageEnhance

from spire_painter.constants import (
    DEFAULT_FONT, MAX_CROP_DISPLAY, MIN_SELECTION_SIZE, SCREEN_DIM_FACTOR,
)


class ToggleSwitch(tk.Canvas):
    """Modern rounded toggle switch for left/right click mode."""

    def __init__(self, parent, command=None, *args, **kwargs):
        super().__init__(parent, width=64, height=28, highlightthickness=0, bg=parent.cget("bg"), *args, **kwargs)
        self.command = command
        self.is_left_click = False

        self.bg_right = "#2196F3"
        self.bg_left = "#4CAF50"
        self.thumb_color = "#FFFFFF"

        self.bind("<Button-1>", self.toggle)
        self.draw()

    def draw(self):
        self.delete("all")
        bg_color = self.bg_left if self.is_left_click else self.bg_right

        self.create_oval(2, 2, 26, 26, fill=bg_color, outline=bg_color)
        self.create_oval(38, 2, 62, 26, fill=bg_color, outline=bg_color)
        self.create_rectangle(14, 2, 50, 26, fill=bg_color, outline=bg_color)

        if self.is_left_click:
            self.create_oval(2, 2, 26, 26, fill=self.thumb_color, outline="")
            self.create_text(46, 14, text="L", fill="white", font=(DEFAULT_FONT, 10, "bold"))
        else:
            self.create_oval(38, 2, 62, 26, fill=self.thumb_color, outline="")
            self.create_text(18, 14, text="R", fill="white", font=(DEFAULT_FONT, 10, "bold"))

    def toggle(self, event=None):
        self.is_left_click = not self.is_left_click
        self.draw()
        if self.command:
            self.command(self.is_left_click)

    def set_state(self, is_left_click):
        self.is_left_click = is_left_click
        self.draw()


class CropOverlay:
    """Popup for interactively cropping line art images."""

    def __init__(self, master, img_path, callback):
        self.top = tk.Toplevel(master)
        self.top.title("Crop Line Art (Hold left click to select, release to finish)")
        self.top.attributes('-topmost', True)
        self.callback = callback
        self.img_path = img_path

        self.original_pil = Image.open(img_path)
        self.display_pil = self.original_pil.copy()

        self.display_pil.thumbnail(MAX_CROP_DISPLAY, Image.Resampling.LANCZOS)

        self.scale_x = self.original_pil.width / self.display_pil.width
        self.scale_y = self.original_pil.height / self.display_pil.height

        self.tk_img = ImageTk.PhotoImage(self.display_pil)

        w = self.display_pil.width
        h = self.display_pil.height
        screen_w = master.winfo_screenwidth()
        screen_h = master.winfo_screenheight()
        x = int((screen_w / 2) - (w / 2))
        y = int((screen_h / 2) - (h / 2))
        self.top.geometry(f"{w}x{h}+{x}+{y}")

        self.canvas = tk.Canvas(self.top, width=w, height=h, cursor="crosshair")
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW)

        self.rect_id = None
        self.start_x = None
        self.start_y = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline='blue', width=2, dash=(4, 4)
        )

    def on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        if not self.start_x or not self.start_y:
            return
        end_x, end_y = event.x, event.y
        rx = min(self.start_x, end_x)
        ry = min(self.start_y, end_y)
        rw = abs(self.start_x - end_x)
        rh = abs(self.start_y - end_y)

        self.top.destroy()

        if rw > MIN_SELECTION_SIZE and rh > MIN_SELECTION_SIZE:
            orig_x = int(rx * self.scale_x)
            orig_y = int(ry * self.scale_y)
            orig_w = int(rw * self.scale_x)
            orig_h = int(rh * self.scale_y)

            cropped = self.original_pil.crop((orig_x, orig_y, orig_x + orig_w, orig_y + orig_h))

            output_dir = os.path.dirname(self.img_path)
            time_str = time.strftime("%Y%m%d_%H%M%S")
            new_path = os.path.join(output_dir, f"cropped_{time_str}.png")

            cropped.save(new_path)
            self.callback(new_path)


class DigitalAmberOverlay:
    """Fullscreen screen-freeze selection overlay with adjustable selection."""

    HANDLE_SIZE = 8
    HANDLE_HALF = 4

    def __init__(self, master, target_image_path, callback, mode="lineart"):
        self.master = master
        self.target_image_path = target_image_path
        self.callback = callback
        self.mode = mode

        self.top = tk.Toplevel(master)
        self.top.overrideredirect(True)
        self.top.attributes('-topmost', True)
        self.top.config(cursor="cross")

        self.v_left = ctypes.windll.user32.GetSystemMetrics(76)
        self.v_top = ctypes.windll.user32.GetSystemMetrics(77)
        v_width = ctypes.windll.user32.GetSystemMetrics(78)
        v_height = ctypes.windll.user32.GetSystemMetrics(79)

        if v_width == 0:
            v_width = self.top.winfo_screenwidth()
            v_height = self.top.winfo_screenheight()
            self.v_left = 0
            self.v_top = 0

        self.top.geometry(f"{v_width}x{v_height}+{self.v_left}+{self.v_top}")

        try:
            screen_img = ImageGrab.grab(all_screens=True)
        except (OSError, ValueError):
            screen_img = ImageGrab.grab()

        enhancer = ImageEnhance.Brightness(screen_img)
        self.dimmed_img = enhancer.enhance(SCREEN_DIM_FACTOR)
        self.tk_img = ImageTk.PhotoImage(self.dimmed_img)

        self.canvas = tk.Canvas(self.top, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW)

        self.outline_color = '#00FF00' if self.mode == "fill" else '#FF4444'
        self.handle_color = '#FFFFFF'

        # Load line art for preview (not applicable to fill mode)
        self.lineart_img = None
        if self.mode != "fill" and target_image_path and os.path.exists(target_image_path):
            try:
                self.lineart_img = Image.open(target_image_path).convert("RGBA")
            except Exception:
                pass

        # Selection state
        self.rect_id = None
        self.handle_ids = []
        self.preview_img_id = None
        self.preview_tk_img = None
        self.hint_id = None
        self.btn_frame = None
        self.start_x = None
        self.start_y = None

        # Adjustment state
        self.phase = "drawing"  # "drawing" -> "adjusting"
        self.drag_action = None  # "move", "nw", "ne", "sw", "se"
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        # Current rect coords (canvas-relative)
        self.rx = 0
        self.ry = 0
        self.rw = 0
        self.rh = 0

        self._show_hint()

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.top.bind("<Return>", lambda e: self._confirm())
        self.top.bind("<Escape>", lambda e: self._cancel())

    def _show_hint(self):
        cw = int(self.top.geometry().split('+')[0].split('x')[0])
        ch = int(self.top.geometry().split('+')[0].split('x')[1])
        self.hint_id = self.canvas.create_text(
            cw // 2, 40,
            text="Click and drag to select area  |  Esc to cancel",
            fill="white", font=(DEFAULT_FONT, 12, "bold")
        )

    def _hide_hint(self):
        if self.hint_id:
            self.canvas.delete(self.hint_id)
            self.hint_id = None

    # ------------------------------------------------------------------
    # Phase 1: Drawing the initial rectangle
    # ------------------------------------------------------------------

    def _on_press(self, event):
        if self.phase == "drawing":
            self._hide_hint()
            self.start_x = event.x
            self.start_y = event.y
            if self.rect_id:
                self.canvas.delete(self.rect_id)
                self._clear_handles()
            self.rect_id = self.canvas.create_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y,
                outline=self.outline_color, width=2
            )
        elif self.phase == "adjusting":
            self._start_adjust(event)

    def _on_drag(self, event):
        if self.phase == "drawing" and self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)
        elif self.phase == "adjusting" and self.drag_action:
            self._do_adjust(event)

    def _on_release(self, event):
        if self.phase == "drawing":
            self._finish_drawing(event)
        elif self.phase == "adjusting":
            self.drag_action = None
            self.top.config(cursor="cross")

    def _finish_drawing(self, event):
        end_x, end_y = event.x, event.y
        self.rx = min(self.start_x, end_x)
        self.ry = min(self.start_y, end_y)
        self.rw = abs(self.start_x - end_x)
        self.rh = abs(self.start_y - end_y)

        if self.rw <= MIN_SELECTION_SIZE or self.rh <= MIN_SELECTION_SIZE:
            return

        self.phase = "adjusting"
        self._update_rect()
        self._draw_handles()
        self._show_buttons()

    # ------------------------------------------------------------------
    # Phase 2: Adjusting the selection
    # ------------------------------------------------------------------

    def _update_rect(self):
        self.canvas.coords(self.rect_id, self.rx, self.ry, self.rx + self.rw, self.ry + self.rh)
        self._draw_handles()
        self._update_preview()

    def _draw_handles(self):
        self._clear_handles()
        h = self.HANDLE_HALF
        corners = [
            (self.rx, self.ry, "nw"),
            (self.rx + self.rw, self.ry, "ne"),
            (self.rx, self.ry + self.rh, "sw"),
            (self.rx + self.rw, self.ry + self.rh, "se"),
        ]
        for cx, cy, tag in corners:
            hid = self.canvas.create_rectangle(
                cx - h, cy - h, cx + h, cy + h,
                fill=self.handle_color, outline=self.outline_color, width=1, tags=tag
            )
            self.handle_ids.append(hid)

    def _clear_handles(self):
        for hid in self.handle_ids:
            self.canvas.delete(hid)
        self.handle_ids.clear()

    def _update_preview(self):
        """Render a semi-transparent preview of the line art inside the selection."""
        if not self.lineart_img or self.rw <= 0 or self.rh <= 0:
            return

        rw, rh = int(self.rw), int(self.rh)
        img_w, img_h = self.lineart_img.size
        scale = min(rw / img_w, rh / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        resized = self.lineart_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Make it semi-transparent so you can see the screen behind it
        if resized.mode == "RGBA":
            r, g, b, a = resized.split()
            a = a.point(lambda x: int(x * 0.5))
            resized = Image.merge("RGBA", (r, g, b, a))
        else:
            resized.putalpha(128)

        self.preview_tk_img = ImageTk.PhotoImage(resized)

        cx = self.rx + self.rw / 2
        cy = self.ry + self.rh / 2

        if self.preview_img_id:
            self.canvas.coords(self.preview_img_id, cx, cy)
            self.canvas.itemconfig(self.preview_img_id, image=self.preview_tk_img)
        else:
            self.preview_img_id = self.canvas.create_image(
                cx, cy, image=self.preview_tk_img, anchor="center"
            )

        # Keep rect and handles above the preview
        if self.rect_id:
            self.canvas.tag_raise(self.rect_id)
        for hid in self.handle_ids:
            self.canvas.tag_raise(hid)

    def _clear_preview(self):
        if self.preview_img_id:
            self.canvas.delete(self.preview_img_id)
            self.preview_img_id = None
            self.preview_tk_img = None

    def _hit_test(self, ex, ey):
        """Determine what the user clicked: a corner handle or the rect body."""
        margin = self.HANDLE_SIZE + 4
        corners = {
            "nw": (self.rx, self.ry),
            "ne": (self.rx + self.rw, self.ry),
            "sw": (self.rx, self.ry + self.rh),
            "se": (self.rx + self.rw, self.ry + self.rh),
        }
        for tag, (cx, cy) in corners.items():
            if abs(ex - cx) <= margin and abs(ey - cy) <= margin:
                return tag

        if self.rx <= ex <= self.rx + self.rw and self.ry <= ey <= self.ry + self.rh:
            return "move"
        return None

    def _start_adjust(self, event):
        action = self._hit_test(event.x, event.y)
        if action == "move":
            self.drag_action = "move"
            self.drag_offset_x = event.x - self.rx
            self.drag_offset_y = event.y - self.ry
            self.top.config(cursor="fleur")
        elif action in ("nw", "ne", "sw", "se"):
            self.drag_action = action
            cursor_map = {"nw": "top_left_corner", "ne": "top_right_corner",
                          "sw": "bottom_left_corner", "se": "bottom_right_corner"}
            self.top.config(cursor=cursor_map[action])
        else:
            # Clicked outside — restart drawing
            self.phase = "drawing"
            self._clear_handles()
            self._clear_preview()
            self._hide_buttons()
            self._on_press(event)

    def _do_adjust(self, event):
        ex, ey = event.x, event.y
        if self.drag_action == "move":
            self.rx = ex - self.drag_offset_x
            self.ry = ey - self.drag_offset_y
        elif self.drag_action == "nw":
            new_rw = (self.rx + self.rw) - ex
            new_rh = (self.ry + self.rh) - ey
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self.rx = ex
                self.ry = ey
                self.rw = new_rw
                self.rh = new_rh
        elif self.drag_action == "ne":
            new_rw = ex - self.rx
            new_rh = (self.ry + self.rh) - ey
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self.ry = ey
                self.rw = new_rw
                self.rh = new_rh
        elif self.drag_action == "sw":
            new_rw = (self.rx + self.rw) - ex
            new_rh = ey - self.ry
            if new_rw > MIN_SELECTION_SIZE and new_rh > MIN_SELECTION_SIZE:
                self.rx = ex
                self.rw = new_rw
                self.rh = new_rh
        elif self.drag_action == "se":
            new_rw = ex - self.rx
            new_rh = ey - self.ry
            if new_rw > MIN_SELECTION_SIZE:
                self.rw = new_rw
            if new_rh > MIN_SELECTION_SIZE:
                self.rh = new_rh

        self._update_rect()
        self._update_button_pos()

    # ------------------------------------------------------------------
    # Confirm / Cancel buttons
    # ------------------------------------------------------------------

    def _show_buttons(self):
        self.btn_frame = tk.Frame(self.canvas, bg="")
        btn_confirm = tk.Button(
            self.btn_frame, text="✓ Draw Here", font=(DEFAULT_FONT, 10, "bold"),
            bg="#4CAF50", fg="white", relief="flat", padx=16, pady=4,
            activebackground="#388E3C", activeforeground="white",
            command=self._confirm, cursor="hand2"
        )
        btn_confirm.pack(side="left", padx=(0, 8))

        btn_cancel = tk.Button(
            self.btn_frame, text="✕ Cancel", font=(DEFAULT_FONT, 10),
            bg="#666666", fg="white", relief="flat", padx=12, pady=4,
            activebackground="#444444", activeforeground="white",
            command=self._cancel, cursor="hand2"
        )
        btn_cancel.pack(side="left")

        btn_redraw = tk.Button(
            self.btn_frame, text="↺ Redraw", font=(DEFAULT_FONT, 10),
            bg="#2196F3", fg="white", relief="flat", padx=12, pady=4,
            activebackground="#1976D2", activeforeground="white",
            command=self._redraw, cursor="hand2"
        )
        btn_redraw.pack(side="left", padx=(8, 0))

        self._update_button_pos()

    def _update_button_pos(self):
        if not self.btn_frame:
            return
        # Place buttons centered below the selection
        cx = self.rx + self.rw // 2
        cy = self.ry + self.rh + 20
        self.canvas.create_window(cx, cy, window=self.btn_frame, anchor="n", tags="btn_window")
        # Clean up old button window positions
        for item in self.canvas.find_withtag("btn_window"):
            if item != self.canvas.find_withtag("btn_window")[-1]:
                self.canvas.delete(item)

    def _hide_buttons(self):
        if self.btn_frame:
            self.btn_frame.destroy()
            self.btn_frame = None
        self.canvas.delete("btn_window")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _confirm(self):
        if self.rw <= MIN_SELECTION_SIZE or self.rh <= MIN_SELECTION_SIZE:
            return
        rx, ry, rw, rh = int(self.rx), int(self.ry), int(self.rw), int(self.rh)
        self.top.destroy()
        abs_rx = self.v_left + rx
        abs_ry = self.v_top + ry
        self.callback(abs_rx, abs_ry, rw, rh, self.target_image_path, self.mode)

    def _cancel(self):
        self.top.destroy()

    def _redraw(self):
        """Reset to drawing phase."""
        self.phase = "drawing"
        self._clear_handles()
        self._clear_preview()
        self._hide_buttons()
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None
        self._show_hint()
