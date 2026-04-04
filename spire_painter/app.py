import os
import time
import ctypes
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from spire_painter.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, APP_ID, BG_COLOR, ACCENT_BLUE,
    TEXT_COLOR, BORDER_COLOR, DEFAULT_FONT, OVERLAY_LAUNCH_DELAY, TUTORIAL_POPUP_DELAY,
)
from spire_painter.drawing_state import state
from spire_painter.config import load_config, save_config as save_config_file, AppConfig
from spire_painter.image_processing import generate_lineart, simulate_drawing, optimize_settings
from spire_painter.drawing_engine import draw_contours
from spire_painter.widgets import DigitalAmberOverlay
from spire_painter.preview_panel import PreviewPanel
from spire_painter.ui import (
    TopBar, ImageSourcePanel, DrawingSettingsPanel, PreviewActions,
    show_tutorial, snap_slider,
)


class SpirePainterApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()
        self.root.title("Slay the Spire 2 - Painter")
        self.root.configure(bg=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self._setup_styles()
        self._setup_output_dir()
        self._setup_icon()
        self._center_window()

        self.current_lineart_path = None
        self.last_raw_image_path = None
        self._lineart_refresh_id = None
        self._preview_refresh_id = None

        # Eraser refinement disabled — StS2 eraser is much thicker than the
        # pen and its width is unknown, so erasing reliably is not possible.
        self.eraser_refine_var = tk.BooleanVar(value=False)

        self.config_path = os.path.join(self.output_dir, "config.json")
        self.app_config = load_config(self.config_path)
        self.is_first_run = self.app_config.is_first_run
        self.topmost_var = tk.BooleanVar(value=self.app_config.topmost)
        self.root.attributes('-topmost', self.topmost_var.get())

        self._build_layout()

        self.root.deiconify()
        self.root.update()
        self.preview.show_hint()

        if self.is_first_run:
            self.root.after(TUTORIAL_POPUP_DELAY, self._on_first_run)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_styles(self):
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure("TLabelframe", background=BG_COLOR, bordercolor=BORDER_COLOR)
        style.configure("TLabelframe.Label", background=BG_COLOR,
                        font=(DEFAULT_FONT, 9, "bold"), foreground=TEXT_COLOR)
        style.map('TCombobox',
                  fieldbackground=[('readonly', '#FFFDF2')],
                  selectbackground=[('readonly', '#FFE0B2')],
                  selectforeground=[('readonly', '#E65100')],
                  background=[('readonly', BG_COLOR)],
                  foreground=[('readonly', TEXT_COLOR)])
        style.configure("Blue.Horizontal.TScale", troughcolor="#BBDEFB",
                        background=ACCENT_BLUE, lightcolor=ACCENT_BLUE,
                        darkcolor=ACCENT_BLUE, bordercolor=BG_COLOR)

    def _setup_output_dir(self):
        self.output_dir = "output_lines"
        os.makedirs(self.output_dir, exist_ok=True)
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

    def _setup_icon(self):
        for ipath in ["brush.ico", os.path.join("output_lines", "brush.ico")]:
            if os.path.exists(ipath):
                try:
                    self.root.iconbitmap(ipath)
                    break
                except Exception:
                    pass

    def _center_window(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}"
                           f"+{(sw - WINDOW_WIDTH) // 2}+{(sh - WINDOW_HEIGHT) // 2}")

    # ------------------------------------------------------------------
    # Layout — assembles UI panels
    # ------------------------------------------------------------------

    def _build_layout(self):
        cfg = self.app_config

        self.root.grid_columnconfigure(0, weight=3, uniform="main")
        self.root.grid_columnconfigure(1, weight=7, uniform="main")
        self.root.grid_rowconfigure(0, weight=1)

        left = tk.Frame(self.root, bg=BG_COLOR)
        left.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        right = tk.Frame(self.root, bg="white", highlightbackground=BORDER_COLOR, highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        right.grid_propagate(False)

        # Start button (bottom)
        self.btn_start = tk.Button(left, text="Start Drawing", bg="#4CAF50", fg="white",
                                   font=(DEFAULT_FONT, 11, "bold"),
                                   command=self.start_digital_amber, state=tk.DISABLED,
                                   height=2, relief="flat", activebackground="#45A049",
                                   activeforeground="white", cursor="hand2")
        self.btn_start.pack(side="bottom", fill="x", padx=10, pady=(0, 5))

        # Panels
        self.top_bar = TopBar(left, self.topmost_var, self.save_config)

        self.image_source = ImageSourcePanel(
            left, cfg,
            on_detail_change=self.on_detail_change,
            on_thickness_change=self.on_thickness_change,
            on_blur_change=self.on_blur_change,
            on_min_contour_change=self.on_min_contour_change,
            on_select_image=self.select_image,
            on_refresh=self.generate_image_lineart,
            on_load_existing=self.load_existing_lineart,
            on_optimize=self.run_optimize,
            on_bg_removal_toggle=self.on_bg_removal_toggle,
        )

        self.draw_settings = DrawingSettingsPanel(
            left, cfg,
            on_speed_change=self.on_speed_change,
            on_brush_change=self.on_brush_change,
            on_edge_close_change=self.on_edge_close_change,
            on_draw_mode_change=self.save_config,
        )

        self.preview_actions = PreviewActions(
            right, on_crop=self.start_crop, on_save=self.save_current_lineart,
            on_open_folder=self.open_output_folder,
        )

        self.preview = PreviewPanel(right, on_image_loaded=self.preview_actions.enable)

    # ------------------------------------------------------------------
    # Slider handlers
    # ------------------------------------------------------------------

    def on_detail_change(self, val):
        if not hasattr(self, 'image_source'):
            return
        imgs = self.image_source
        if snap_slider(imgs.detail_slider, imgs.detail_entry, imgs.detail_var, val):
            self.save_config()
            self._schedule_lineart_refresh()

    def on_thickness_change(self, val):
        if not hasattr(self, 'image_source'):
            return
        imgs = self.image_source
        if snap_slider(imgs.thickness_slider, imgs.thickness_entry, imgs.thickness_var, val):
            self.save_config()
            self._schedule_lineart_refresh()

    def on_speed_change(self, val):
        if not hasattr(self, 'draw_settings'):
            return
        ds = self.draw_settings
        if snap_slider(ds.speed_slider, ds.speed_entry, ds.speed_var, val):
            self.save_config()
            self._schedule_preview_refresh()

    def on_brush_change(self, val):
        if not hasattr(self, 'draw_settings'):
            return
        ds = self.draw_settings
        if snap_slider(ds.brush_slider, ds.brush_entry, ds.brush_var, val, " px"):
            self.save_config()
            self._schedule_preview_refresh()

    def on_edge_close_change(self, val):
        if not hasattr(self, 'draw_settings'):
            return
        v = round(float(val))
        if v > 1 and v % 2 == 0:
            v += 1
        ds = self.draw_settings
        if snap_slider(ds.edge_close_slider, ds.edge_close_entry, ds.edge_close_var, v):
            self.save_config()
            self._schedule_preview_refresh()

    def on_bg_removal_toggle(self):
        if not hasattr(self, 'image_source'):
            return
        self.save_config()
        self._schedule_lineart_refresh()

    def on_blur_change(self, val):
        if not hasattr(self, 'image_source'):
            return
        v = round(float(val))
        if v > 1 and v % 2 == 0:
            v += 1
        imgs = self.image_source
        if snap_slider(imgs.blur_slider, imgs.blur_entry, imgs.blur_var, v):
            self.save_config()
            self._schedule_lineart_refresh()

    def on_min_contour_change(self, val):
        if not hasattr(self, 'image_source'):
            return
        imgs = self.image_source
        if snap_slider(imgs.min_contour_slider, imgs.min_contour_entry, imgs.min_contour_var, val):
            self.save_config()
            self._schedule_lineart_refresh()

    # ------------------------------------------------------------------
    # Debounced refresh
    # ------------------------------------------------------------------

    def _schedule_lineart_refresh(self):
        if self._lineart_refresh_id is not None:
            self.root.after_cancel(self._lineart_refresh_id)
        if self.last_raw_image_path:
            self._lineart_refresh_id = self.root.after(500, self._do_lineart_refresh)

    def _do_lineart_refresh(self):
        self._lineart_refresh_id = None
        if self.last_raw_image_path:
            self.generate_image_lineart()

    def _schedule_preview_refresh(self):
        if self._preview_refresh_id is not None:
            self.root.after_cancel(self._preview_refresh_id)
        if self.current_lineart_path:
            self._preview_refresh_id = self.root.after(300, self._do_preview_refresh)

    def _do_preview_refresh(self):
        self._preview_refresh_id = None
        self._refresh_simulated_preview()

    def _refresh_simulated_preview(self):
        if not self.current_lineart_path or not os.path.exists(self.current_lineart_path):
            return
        ds = self.draw_settings
        imgs = self.image_source
        sim_img = simulate_drawing(
            self.current_lineart_path,
            speed=int(round(float(ds.speed_slider.get()))),
            brush_width=int(round(float(ds.brush_slider.get()))),
            edge_close=int(round(float(ds.edge_close_slider.get()))),
            eraser_refine=self.eraser_refine_var.get(),
            min_contour_len=int(round(float(imgs.min_contour_slider.get()))),
        )
        self.preview.update_from_image(sim_img)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def save_config(self, *_):
        if not hasattr(self, 'image_source'):
            return
        is_top = self.topmost_var.get()
        self.root.attributes('-topmost', is_top)
        imgs = self.image_source
        ds = self.draw_settings
        self.app_config = AppConfig(
            topmost=is_top,
            detail=int(round(float(imgs.detail_slider.get()))),
            speed=int(round(float(ds.speed_slider.get()))),
            thickness=int(round(float(imgs.thickness_slider.get()))),
            brush_width=int(round(float(ds.brush_slider.get()))),
            blur=int(round(float(imgs.blur_slider.get()))),
            min_contour_len=int(round(float(imgs.min_contour_slider.get()))),
            bg_removal=imgs.bg_removal_var.get(),
            draw_mode=ds.draw_mode,
            edge_close=int(round(float(ds.edge_close_slider.get()))),
            eraser_refine=self.eraser_refine_var.get(),
            is_first_run=getattr(self, 'is_first_run', False),
        )
        save_config_file(self.config_path, self.app_config)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def save_current_lineart(self):
        if self.current_lineart_path and os.path.exists(self.current_lineart_path):
            time_str = time.strftime("%Y%m%d_%H%M%S")
            new_path = os.path.join(self.output_dir, f"saved_{time_str}.png")
            try:
                shutil.copy(self.current_lineart_path, new_path)
                self.current_lineart_path = new_path
                self.top_bar.update_status(f"Saved: {os.path.basename(new_path)}")
            except Exception as e:
                messagebox.showerror("Save Failed", f"Unable to save file: {e}")

    def start_crop(self):
        if self.current_lineart_path:
            self.preview.enter_crop_mode(self._finish_crop)

    def _finish_crop(self, cropped_pil_image):
        time_str = time.strftime("%Y%m%d_%H%M%S")
        new_path = os.path.join(self.output_dir, f"cropped_{time_str}.png")
        cropped_pil_image.save(new_path)
        self.current_lineart_path = new_path
        self.top_bar.update_status(f"Cropped: {os.path.basename(new_path)}")
        self._refresh_simulated_preview()

    def open_output_folder(self):
        try:
            os.startfile(os.path.abspath(self.output_dir))
        except Exception as e:
            messagebox.showerror("Error", f"Unable to open folder: {e}")

    # ------------------------------------------------------------------
    # Image loading / generation
    # ------------------------------------------------------------------

    def select_image(self):
        state.trigger_abort()
        file_path = filedialog.askopenfilename(title="Select Source Image",
                                               filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        if file_path:
            self.last_raw_image_path = file_path
            self.image_source.btn_reprocess.config(state=tk.NORMAL)
            self.image_source.btn_optimize.config(state=tk.NORMAL)
            self.generate_image_lineart()

    def generate_image_lineart(self):
        state.trigger_abort()
        if not self.last_raw_image_path:
            return
        imgs = self.image_source
        detail = int(round(float(imgs.detail_slider.get())))
        thickness = int(round(float(imgs.thickness_slider.get())))
        blur = int(round(float(imgs.blur_slider.get())))
        min_len = int(round(float(imgs.min_contour_slider.get())))
        bg_removal = imgs.bg_removal_var.get()
        save_path = generate_lineart(self.last_raw_image_path, detail, self.output_dir,
                                     thickness, blur, min_len, bg_removal)
        self.current_lineart_path = save_path
        self.top_bar.update_status(f"Line art generated (detail: {detail})")
        self.btn_start.config(state=tk.NORMAL)
        self._refresh_simulated_preview()

    def run_optimize(self):
        if not self.last_raw_image_path:
            return

        # Create progress bar popup
        popup = tk.Toplevel(self.root)
        popup.title("Optimizing")
        popup.resizable(False, False)
        popup.attributes('-topmost', True)
        popup.grab_set()

        pw, ph = 350, 80
        x = self.root.winfo_x() + (self.root.winfo_width() - pw) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{x}+{y}")

        tk.Label(popup, text="Finding optimal settings...",
                 font=(DEFAULT_FONT, 10)).pack(pady=(10, 5))
        progress = ttk.Progressbar(popup, length=300, mode='determinate')
        progress.pack(padx=25, pady=(0, 10))

        def update_progress(frac):
            progress['value'] = frac * 100
            popup.update()

        try:
            params = optimize_settings(self.last_raw_image_path, self.output_dir,
                                       on_progress=update_progress)
        except Exception as e:
            popup.destroy()
            messagebox.showerror("Optimize Failed", str(e))
            return

        popup.destroy()

        if not params:
            self.top_bar.update_status("Optimization found no improvement.")
            return

        # Apply optimized values to sliders
        imgs = self.image_source
        imgs.detail_slider.set(params['detail'])
        imgs.blur_slider.set(params['blur'])
        imgs.min_contour_slider.set(params['min_contour_len'])
        imgs.thickness_slider.set(params['thickness'])
        imgs.bg_removal_var.set(params.get('bg_removal', False))
        self.draw_settings.edge_close_slider.set(params['edge_close'])
        self.draw_settings.speed_slider.set(params.get('speed', 2))

        self.save_config()
        self.generate_image_lineart()

        bg_str = ", bg removed" if params.get('bg_removal') else ""
        self.top_bar.update_status(
            f"Optimized: detail={params['detail']}, blur={params['blur']}, "
            f"speed={params.get('speed', 2)}, min_len={params['min_contour_len']}{bg_str}")

    def load_existing_lineart(self):
        state.trigger_abort()
        file_path = filedialog.askopenfilename(
            initialdir=os.path.abspath(self.output_dir),
            title="Select Saved Line Art",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")]
        )
        if file_path:
            self.current_lineart_path = file_path
            self.top_bar.update_status(f"Loaded: {os.path.basename(file_path)}")
            self.btn_start.config(state=tk.NORMAL)
            self._refresh_simulated_preview()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def start_digital_amber(self):
        state.trigger_abort()
        self.root.iconify()
        self.root.after(OVERLAY_LAUNCH_DELAY, self._launch_overlay)

    def _launch_overlay(self):
        state.reset()
        ds = self.draw_settings
        step = int(round(float(ds.speed_slider.get())))
        draw_mode = ds.draw_mode
        edge_close = int(round(float(ds.edge_close_slider.get())))
        eraser_refine = self.eraser_refine_var.get()
        brush_width = int(round(float(ds.brush_slider.get())))

        DigitalAmberOverlay(
            self.root, self.current_lineart_path,
            lambda rx, ry, rw, rh, img_path, _: self._run_draw(
                rx, ry, rw, rh, img_path, step, draw_mode, edge_close, eraser_refine, brush_width),
            mode="lineart"
        )

    def _run_draw(self, rx, ry, rw, rh, img_path, step, draw_mode, edge_close, eraser_refine, brush_width):
        threading.Thread(
            target=draw_contours,
            args=(state, rx, ry, rw, rh, img_path, step, draw_mode, edge_close, eraser_refine, brush_width),
            daemon=True
        ).start()

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def on_closing(self):
        state.trigger_abort()
        time.sleep(0.1)
        self.root.destroy()

    def _on_first_run(self):
        def done():
            self.is_first_run = False
            self.save_config()
        show_tutorial(self.root, done)


def main():
    root = tk.Tk()
    SpirePainterApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
