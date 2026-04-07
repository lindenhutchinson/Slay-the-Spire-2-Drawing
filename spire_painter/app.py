import os
import time
import ctypes
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from dataclasses import asdict

from PIL import Image

from spire_painter.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, APP_ID, BG_COLOR, ACCENT_BLUE,
    TEXT_COLOR, BORDER_COLOR, DEFAULT_FONT, OVERLAY_LAUNCH_DELAY, TUTORIAL_POPUP_DELAY,
    MAX_UNDO_HISTORY,
)
from spire_painter.drawing_state import state, setup_hotkeys, cleanup_hotkeys
from spire_painter.config import (
    load_config, save_config as save_config_file, AppConfig,
    list_presets, save_preset, load_preset, delete_preset,
)
from spire_painter.image_processing import generate_lineart, simulate_drawing, optimize_settings
from spire_painter.drawing_engine import draw_contours
from spire_painter.widgets import DigitalAmberOverlay
from spire_painter.preview_panel import PreviewPanel
from spire_painter.ui import (
    TopBar, ImageSourcePanel, DrawingSettingsPanel, PreviewActions,
    show_tutorial, snap_slider, snap_float_slider,
)


# ---------------------------------------------------------
# Settings undo/redo history
# ---------------------------------------------------------

class SettingsHistory:
    """Stores snapshots of AppConfig for undo/redo."""

    def __init__(self, max_size=MAX_UNDO_HISTORY):
        self._history: list[dict] = []
        self._index = -1
        self._max_size = max_size

    def push(self, config: AppConfig):
        # Truncate any redo history
        self._history = self._history[:self._index + 1]
        self._history.append(asdict(config))
        if len(self._history) > self._max_size:
            self._history.pop(0)
        self._index = len(self._history) - 1

    def undo(self) -> dict | None:
        if self._index > 0:
            self._index -= 1
            return self._history[self._index].copy()
        return None

    def redo(self) -> dict | None:
        if self._index < len(self._history) - 1:
            self._index += 1
            return self._history[self._index].copy()
        return None


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
        self._progress_poll_id = None

        self.config_path = os.path.join(self.output_dir, "config.json")
        self.app_config = load_config(self.config_path)
        self.is_first_run = self.app_config.is_first_run
        self.topmost_var = tk.BooleanVar(value=self.app_config.topmost)
        self.root.attributes('-topmost', self.topmost_var.get())

        self._draw_thread = None
        self._history = SettingsHistory()

        self._build_layout()

        # Push initial config to history
        self._history.push(self.app_config)

        # Bind undo/redo
        self.root.bind("<Control-z>", self._undo_settings)
        self.root.bind("<Control-y>", self._redo_settings)

        setup_hotkeys()

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

        # Preset bar (above start button)
        self._build_preset_bar(left)

        # Panels
        self.top_bar = TopBar(left, self.topmost_var, self.save_config)

        self.image_source = ImageSourcePanel(
            left, cfg,
            on_detail_change=self.on_detail_change,
            on_thickness_change=self.on_thickness_change,
            on_blur_change=self.on_blur_change,
            on_min_contour_change=self.on_min_contour_change,
            on_clahe_change=self.on_clahe_change,
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
            on_bezier_toggle=self._on_checkbox_save,
            on_hatching_toggle=self._on_checkbox_preview,
            on_hatching_density_change=self._on_hatching_density_change,
            on_multi_res_toggle=self._on_checkbox_save,
            on_eraser_refine_toggle=self._on_checkbox_save,
            on_eraser_width_change=self._on_eraser_width_change,
        )

        self.preview_actions = PreviewActions(
            right, on_crop=self.start_crop, on_save=self.save_current_lineart,
            on_open_folder=self.open_output_folder,
            on_side_by_side=self._toggle_side_by_side,
        )

        self.preview = PreviewPanel(right, on_image_loaded=self.preview_actions.enable)

    def _build_preset_bar(self, parent):
        """Build the preset save/load/delete bar."""
        frame = tk.Frame(parent, bg=BG_COLOR)
        frame.pack(side="bottom", fill="x", padx=10, pady=(0, 5))

        tk.Label(frame, text="Preset:", bg=BG_COLOR, font=(DEFAULT_FONT, 9)).pack(side="left")

        self.preset_combo = ttk.Combobox(frame, state="readonly", width=14, font=(DEFAULT_FONT, 9))
        self.preset_combo.pack(side="left", padx=(5, 3))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)
        self._refresh_preset_list()

        from spire_painter.ui.helpers import flat_button
        flat_button(frame, "Save", self._save_preset,
                    bg="#E8F5E9", active_bg="#C8E6C9", fg="#1B5E20").pack(side="left", padx=(0, 3))
        flat_button(frame, "Delete", self._delete_preset,
                    bg="#FFEBEE", active_bg="#FFCDD2", fg="#B71C1C").pack(side="left")

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
        imgs = self.image_source
        v = round(float(val))
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

    def on_clahe_change(self, val):
        if not hasattr(self, 'image_source'):
            return
        imgs = self.image_source
        if snap_float_slider(imgs.clahe_slider, imgs.clahe_entry, imgs.clahe_var, val, resolution=0.5):
            self.save_config()
            self._schedule_lineart_refresh()

    def _on_checkbox_save(self):
        """Generic handler for checkboxes that just save config."""
        self.save_config()

    def _on_checkbox_preview(self):
        """Handler for checkboxes that affect the preview."""
        self.save_config()
        self._schedule_preview_refresh()

    def _on_hatching_density_change(self, val):
        if not hasattr(self, 'draw_settings'):
            return
        ds = self.draw_settings
        if snap_slider(ds.hatching_density_slider, ds.hatching_density_entry, ds.hatching_density_var, val):
            self.save_config()
            self._schedule_preview_refresh()

    def _on_eraser_width_change(self, val):
        if not hasattr(self, 'draw_settings'):
            return
        ds = self.draw_settings
        if snap_slider(ds.eraser_width_slider, ds.eraser_width_entry, ds.eraser_width_var, val, " px"):
            self.save_config()

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

        # Load source grayscale for hatching preview
        import cv2
        import numpy as np
        source_gray = None
        if ds.hatching_var.get() and self.last_raw_image_path:
            try:
                source_gray = cv2.imdecode(
                    np.fromfile(self.last_raw_image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE
                )
                # Resize to match lineart dimensions
                lineart_img = cv2.imdecode(
                    np.fromfile(self.current_lineart_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE
                )
                if source_gray is not None and lineart_img is not None:
                    source_gray = cv2.resize(source_gray, (lineart_img.shape[1], lineart_img.shape[0]))
            except Exception:
                source_gray = None

        sim_img = simulate_drawing(
            self.current_lineart_path,
            speed=int(round(float(ds.speed_slider.get()))),
            brush_width=int(round(float(ds.brush_slider.get()))),
            edge_close=int(round(float(ds.edge_close_slider.get()))),
            eraser_refine=ds.eraser_refine_var.get(),
            min_contour_len=int(round(float(imgs.min_contour_slider.get()))),
            bezier_fitting=ds.bezier_var.get(),
            hatching_enabled=ds.hatching_var.get(),
            hatching_density=int(round(float(ds.hatching_density_slider.get()))),
            source_gray=source_gray,
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
            eraser_refine=ds.eraser_refine_var.get(),
            eraser_width=int(round(float(ds.eraser_width_slider.get()))),
            is_first_run=getattr(self, 'is_first_run', False),
            clahe_clip=round(float(imgs.clahe_slider.get()) * 2) / 2,  # snap to 0.5
            bezier_fitting=ds.bezier_var.get(),
            hatching_enabled=ds.hatching_var.get(),
            hatching_density=int(round(float(ds.hatching_density_slider.get()))),
            multi_resolution=ds.multi_res_var.get(),
        )
        save_config_file(self.config_path, self.app_config)
        self._history.push(self.app_config)

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _undo_settings(self, event=None):
        state_dict = self._history.undo()
        if state_dict:
            self._apply_settings_dict(state_dict)
            self.top_bar.update_status("Settings undone (Ctrl+Z)")

    def _redo_settings(self, event=None):
        state_dict = self._history.redo()
        if state_dict:
            self._apply_settings_dict(state_dict)
            self.top_bar.update_status("Settings redone (Ctrl+Y)")

    def _apply_settings_dict(self, d):
        """Apply a settings dict to all sliders/checkboxes without triggering save_config."""
        imgs = self.image_source
        ds = self.draw_settings

        imgs.detail_slider.set(d.get('detail', 5))
        imgs.thickness_slider.set(d.get('thickness', 1))
        imgs.blur_slider.set(d.get('blur', 11))
        imgs.min_contour_slider.set(d.get('min_contour_len', 0))
        imgs.clahe_slider.set(d.get('clahe_clip', 0.0))
        imgs.bg_removal_var.set(d.get('bg_removal', False))

        ds.speed_slider.set(d.get('speed', 3))
        ds.brush_slider.set(d.get('brush_width', 3))
        ds.edge_close_slider.set(d.get('edge_close', 3))
        ds.bezier_var.set(d.get('bezier_fitting', False))
        ds.hatching_var.set(d.get('hatching_enabled', False))
        ds.hatching_density_slider.set(d.get('hatching_density', 4))
        ds.multi_res_var.set(d.get('multi_resolution', False))
        ds.eraser_refine_var.set(d.get('eraser_refine', False))
        ds.eraser_width_slider.set(d.get('eraser_width', 10))

        # Rebuild config from dict and save without pushing to history
        self.app_config = AppConfig(**{k: d[k] for k in AppConfig.__dataclass_fields__ if k in d})
        save_config_file(self.config_path, self.app_config)

        # Refresh
        if self.last_raw_image_path:
            self._schedule_lineart_refresh()
        elif self.current_lineart_path:
            self._schedule_preview_refresh()

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def _refresh_preset_list(self):
        names = list_presets(self.output_dir)
        self.preset_combo['values'] = names
        if names:
            self.preset_combo.set(names[0])
        else:
            self.preset_combo.set("")

    def _on_preset_selected(self, event=None):
        name = self.preset_combo.get()
        if not name:
            return
        try:
            d = load_preset(self.output_dir, name)
        except Exception as e:
            messagebox.showerror("Load Failed", str(e))
            return
        self._apply_settings_dict(d)
        self._history.push(self.app_config)
        self.top_bar.update_status(f"Loaded preset: {name}")

    def _save_preset(self):
        name = simpledialog.askstring("Save Preset", "Preset name:",
                                      parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        try:
            save_preset(self.output_dir, name, self.app_config)
        except Exception as e:
            messagebox.showerror("Save Failed", str(e))
            return
        self._refresh_preset_list()
        self.preset_combo.set(name)
        self.top_bar.update_status(f"Saved preset: {name}")

    def _delete_preset(self):
        name = self.preset_combo.get()
        if not name:
            return
        try:
            delete_preset(self.output_dir, name)
        except Exception as e:
            messagebox.showerror("Delete Failed", str(e))
            return
        self._refresh_preset_list()
        self.top_bar.update_status(f"Deleted preset: {name}")

    # ------------------------------------------------------------------
    # Side-by-side
    # ------------------------------------------------------------------

    def _toggle_side_by_side(self):
        self.preview.toggle_side_by_side()

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
        if not self.last_raw_image_path or not os.path.exists(self.last_raw_image_path):
            return
        source_img = Image.open(self.last_raw_image_path)
        self.preview.enter_crop_mode(
            self._finish_crop,
            source_image=source_img,
            on_enter=self.preview_actions.hide,
            on_exit=self.preview_actions.show,
        )

    def _finish_crop(self, cropped_pil_image):
        time_str = time.strftime("%Y%m%d_%H%M%S")
        cropped_src_path = os.path.join(self.output_dir, f"cropped_src_{time_str}.png")
        cropped_pil_image.save(cropped_src_path)
        self.last_raw_image_path = cropped_src_path
        self.top_bar.update_status(f"Cropped source: {os.path.basename(cropped_src_path)}")
        self.generate_image_lineart()

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

            # Store original for side-by-side
            try:
                self.preview.set_original_image(Image.open(file_path))
            except Exception:
                pass

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
        clahe_clip = round(float(imgs.clahe_slider.get()) * 2) / 2
        save_path = generate_lineart(self.last_raw_image_path, detail, self.output_dir,
                                     thickness, blur, min_len, bg_removal, clahe_clip)
        self.current_lineart_path = save_path
        self.top_bar.update_status(f"Line art generated (detail: {detail})")
        self.btn_start.config(state=tk.NORMAL)
        self._refresh_simulated_preview()

    def run_optimize(self):
        if not self.last_raw_image_path:
            return

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
        imgs.clahe_slider.set(params.get('clahe_clip', 0.0))
        self.draw_settings.edge_close_slider.set(params['edge_close'])
        self.draw_settings.speed_slider.set(params.get('speed', 2))

        self.save_config()
        self.generate_image_lineart()

        bg_str = ", bg removed" if params.get('bg_removal') else ""
        clahe_str = f", clahe={params.get('clahe_clip', 0)}" if params.get('clahe_clip', 0) > 0 else ""
        self.top_bar.update_status(
            f"Optimized: detail={params['detail']}, blur={params['blur']}, "
            f"speed={params.get('speed', 2)}, min_len={params['min_contour_len']}{bg_str}{clahe_str}")

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
        eraser_refine = ds.eraser_refine_var.get()
        brush_width = int(round(float(ds.brush_slider.get())))
        eraser_width = int(round(float(ds.eraser_width_slider.get())))
        bezier_fitting = ds.bezier_var.get()
        hatching_enabled = ds.hatching_var.get()
        hatching_density = int(round(float(ds.hatching_density_slider.get())))
        multi_resolution = ds.multi_res_var.get()

        DigitalAmberOverlay(
            self.root, self.current_lineart_path,
            lambda rx, ry, rw, rh, img_path, _: self._run_draw(
                rx, ry, rw, rh, img_path, step, draw_mode, edge_close,
                eraser_refine, brush_width, eraser_width,
                bezier_fitting, hatching_enabled, hatching_density, multi_resolution),
            mode="lineart"
        )

    def _run_draw(self, rx, ry, rw, rh, img_path, step, draw_mode, edge_close,
                  eraser_refine, brush_width, eraser_width,
                  bezier_fitting, hatching_enabled, hatching_density, multi_resolution):
        self._draw_thread = threading.Thread(
            target=draw_contours,
            args=(state, rx, ry, rw, rh, img_path, step, draw_mode),
            kwargs=dict(
                edge_close=edge_close,
                eraser_refine=eraser_refine,
                brush_width=brush_width,
                eraser_width=eraser_width,
                bezier_fitting=bezier_fitting,
                hatching_enabled=hatching_enabled,
                hatching_density=hatching_density,
                multi_resolution=multi_resolution,
                source_gray_path=self.last_raw_image_path,
            ),
            daemon=True
        )
        self._draw_thread.start()
        self._start_progress_polling()

    # ------------------------------------------------------------------
    # Drawing progress polling
    # ------------------------------------------------------------------

    def _start_progress_polling(self):
        """Start polling drawing progress for ETA display."""
        if self._progress_poll_id is not None:
            self.root.after_cancel(self._progress_poll_id)
        self._progress_poll_id = self.root.after(1000, self._poll_draw_progress)

    def _poll_draw_progress(self):
        """Poll drawing state and update status bar with ETA."""
        self._progress_poll_id = None

        if not state.drawing:
            self.top_bar.update_status("Drawing complete!")
            return

        completed, total, start_time = state.get_progress()

        if total > 0 and completed > 0:
            pct = completed / total * 100
            elapsed = time.time() - start_time
            if elapsed > 0 and completed > total * 0.02:
                eta_secs = elapsed * (total - completed) / completed
                if eta_secs < 60:
                    eta_str = f"{int(eta_secs)}s"
                elif eta_secs < 3600:
                    eta_str = f"{int(eta_secs // 60)}m {int(eta_secs % 60)}s"
                else:
                    eta_str = f"{int(eta_secs // 3600)}h {int((eta_secs % 3600) // 60)}m"
                self.top_bar.update_status(f"Drawing... {pct:.0f}% (~{eta_str} remaining)")
            else:
                self.top_bar.update_status(f"Drawing... {pct:.0f}%")
        else:
            self.top_bar.update_status("Drawing... preparing strokes")

        self._progress_poll_id = self.root.after(1000, self._poll_draw_progress)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def on_closing(self):
        state.trigger_abort()
        if self._progress_poll_id is not None:
            self.root.after_cancel(self._progress_poll_id)
        if self._draw_thread is not None and self._draw_thread.is_alive():
            self._draw_thread.join(timeout=2)
        cleanup_hotkeys()
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
