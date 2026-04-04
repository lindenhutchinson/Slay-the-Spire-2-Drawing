import os
import time
import ctypes
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from spire_painter.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, APP_ID, BG_COLOR, ACCENT_BLUE, ACCENT_GREEN,
    TEXT_COLOR, TEXT_LIGHT, BORDER_COLOR, ALERT_RED, DEFAULT_FONT, FONT_MAP,
    DEFAULT_FILL_GAP,
    OVERLAY_LAUNCH_DELAY, TUTORIAL_POPUP_DELAY,
)
from spire_painter.drawing_state import state
from spire_painter.config import load_config, save_config as save_config_file, AppConfig
from spire_painter.image_processing import generate_lineart, resolve_font, generate_text_lineart
from spire_painter.drawing_engine import draw_contours, draw_fill

from spire_painter.widgets import ToggleSwitch, CropOverlay, DigitalAmberOverlay
from spire_painter.preview_panel import PreviewPanel
from spire_painter.tooltip import Tooltip

# ---------------------------------------------------------
# Main Application Interface
# ---------------------------------------------------------
class SpirePainterApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw() 
        self.root.title("Slay the Spire 2 - Digital Amber Painter")
        self.root.configure(bg=BG_COLOR)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.style = ttk.Style()
        if 'clam' in self.style.theme_names():
            self.style.theme_use('clam')

        self.style.configure("TLabelframe", background=BG_COLOR, bordercolor=BORDER_COLOR)
        self.style.configure("TLabelframe.Label", background=BG_COLOR, font=(DEFAULT_FONT, 9, "bold"), foreground=TEXT_COLOR)

        self.style.map('TCombobox',
            fieldbackground=[('readonly', '#FFFDF2')],
            selectbackground=[('readonly', '#FFE0B2')],
            selectforeground=[('readonly', '#E65100')],
            background=[('readonly', BG_COLOR)],
            foreground=[('readonly', TEXT_COLOR)]
        )

        self.style.configure("Blue.Horizontal.TScale", troughcolor="#BBDEFB", background=ACCENT_BLUE, lightcolor=ACCENT_BLUE, darkcolor=ACCENT_BLUE, bordercolor=BG_COLOR)
        self.style.configure("Green.Horizontal.TScale", troughcolor="#C8E6C9", background=ACCENT_GREEN, lightcolor=ACCENT_GREEN, darkcolor=ACCENT_GREEN, bordercolor=BG_COLOR)

        self.output_dir = "output_lines"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

        icon_paths = ["brush.ico", os.path.join(self.output_dir, "brush.ico")]
        for ipath in icon_paths:
            if os.path.exists(ipath):
                try:
                    self.root.iconbitmap(ipath)
                    break
                except Exception:
                    pass
        
        # Standard 16:9
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        center_x = int((screen_width / 2) - (WINDOW_WIDTH / 2))
        center_y = int((screen_height / 2) - (WINDOW_HEIGHT / 2))
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{center_x}+{center_y}") 
        
        self.current_lineart_path = None
        self.last_raw_image_path = None
        
        self.config_path = os.path.join(self.output_dir, "config.json")
        self.app_config = load_config(self.config_path)
        self.is_first_run = self.app_config.is_first_run

        init_detail = self.app_config.detail
        init_speed = self.app_config.speed
        init_fill_gap = self.app_config.fill_gap
        init_thickness = self.app_config.thickness
        init_is_left_click = self.app_config.is_left_click

        self.topmost_var = tk.BooleanVar(value=self.app_config.topmost)
        self.root.attributes('-topmost', self.topmost_var.get())

        self.font_map = FONT_MAP

        # Force absolute 3:7 physical layout
        self.root.grid_columnconfigure(0, weight=3, uniform="main_layout") 
        self.root.grid_columnconfigure(1, weight=7, uniform="main_layout") 
        self.root.grid_rowconfigure(0, weight=1)    

        self.left_panel = tk.Frame(root, bg=BG_COLOR)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.right_panel = tk.Frame(root, bg="white", highlightbackground=BORDER_COLOR, highlightthickness=1)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        self.right_panel.grid_propagate(False)

        self.btn_start = tk.Button(self.left_panel, text="🚀 Start Drawing (Enter Digital Amber)", bg="#4CAF50", fg="white",
                                   font=(DEFAULT_FONT, 11, "bold"), command=lambda: self.start_digital_amber(mode="lineart"), state=tk.DISABLED, 
                                   height=2, relief="flat", activebackground="#45A049", activeforeground="white", cursor="hand2")
        self.btn_start.pack(side="bottom", fill="x", padx=10, pady=(0, 5))
        Tooltip(self.btn_start, "Freeze the screen and select where to draw. Confirm the area, then drawing begins automatically.")

        top_bar = tk.Frame(self.left_panel, bg=BG_COLOR)
        top_bar.pack(side="top", fill="x", pady=(0, 5))
        
        right_info_frame = tk.Frame(top_bar, bg=BG_COLOR)
        right_info_frame.pack(side="right", anchor="ne")
        
        self.chk_topmost = tk.Checkbutton(right_info_frame, text="📌 Always on Top", font=(DEFAULT_FONT, 9), variable=self.topmost_var, command=self.save_config, bg=BG_COLOR)
        self.chk_topmost.pack(anchor="e")
        Tooltip(self.chk_topmost, "Keep this window above all other windows.")
        
        # Prominent standalone hotkey area (never disappears with status text refresh)
        hotkeys_text = "P: Pause  |  Ctrl+Alt+P: Resume\n[ : Terminate"
        self.lbl_hotkeys = tk.Label(right_info_frame, text=hotkeys_text, fg=ALERT_RED, bg=BG_COLOR, font=(DEFAULT_FONT, 9, "bold"), justify="right")
        self.lbl_hotkeys.pack(anchor="e", pady=(2, 0))
        
        # Output box height compressed to 2 lines, fits 720p perfectly
        self.status_text = tk.Text(top_bar, height=2, bg=BG_COLOR, fg="#1976D2", 
                                   font=(DEFAULT_FONT, 10, "bold"), 
                                   relief="flat", wrap="word", highlightthickness=0)
        self.status_text.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.status_text.insert("1.0", "Please prepare line art first...")
        self.status_text.config(state=tk.DISABLED)

        def create_flat_button(parent, text, command, state=tk.NORMAL, bg="#FFFFFF", active_bg="#EAEAEA", fg=TEXT_COLOR):
            return tk.Button(parent, text=text, command=command, state=state, 
                             relief="solid", bd=1, bg=bg, fg=fg, activebackground=active_bg, activeforeground=fg, 
                             font=(DEFAULT_FONT, 9), cursor="hand2")

        frame1 = ttk.LabelFrame(self.left_panel, text=" Mode A: External Image ", padding=(10, 5))
        frame1.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 2))
        wrap1 = tk.Frame(frame1, bg=BG_COLOR)
        wrap1.pack(expand=True, fill="x")
        detail_frame = tk.Frame(wrap1, bg=BG_COLOR)
        detail_frame.pack(fill="x")
        lbl_detail = tk.Label(detail_frame, text="Detail:", bg=BG_COLOR, font=(DEFAULT_FONT, 9))
        lbl_detail.pack(side="left")
        self.detail_slider = ttk.Scale(detail_frame, from_=1, to=10, orient="horizontal", style="Blue.Horizontal.TScale", command=self.on_detail_change)
        self.detail_slider.set(init_detail)
        self.detail_slider.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_detail_val = tk.Label(detail_frame, text=str(init_detail), font=(DEFAULT_FONT, 10, "bold"), fg="#2196F3", bg=BG_COLOR)
        self.lbl_detail_val.pack(side="left")
        Tooltip(lbl_detail, "How many edges to detect. Higher = more lines, finer detail.")
        Tooltip(self.detail_slider, "How many edges to detect. Higher = more lines, finer detail.")

        thick_frame = tk.Frame(wrap1, bg=BG_COLOR)
        thick_frame.pack(fill="x", pady=(2, 0))
        lbl_thick = tk.Label(thick_frame, text="Thickness:", bg=BG_COLOR, font=(DEFAULT_FONT, 9))
        lbl_thick.pack(side="left")
        self.thickness_slider = ttk.Scale(thick_frame, from_=1, to=7, orient="horizontal", style="Blue.Horizontal.TScale", command=self.on_thickness_change)
        self.thickness_slider.set(init_thickness)
        self.thickness_slider.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_thick_val = tk.Label(thick_frame, text=str(init_thickness), font=(DEFAULT_FONT, 10, "bold"), fg="#2196F3", bg=BG_COLOR)
        self.lbl_thick_val.pack(side="left")
        Tooltip(lbl_thick, "Line thickness. 1 = thin single-pixel edges. Higher values produce bolder strokes.")
        Tooltip(self.thickness_slider, "Line thickness. 1 = thin single-pixel edges. Higher values produce bolder strokes.")

        btn_frame1 = tk.Frame(wrap1, bg=BG_COLOR)
        btn_frame1.pack(fill="x", pady=(5, 0))
        self.btn_image = create_flat_button(btn_frame1, "1. Select Image", self.select_image, bg="#E3F2FD", active_bg="#BBDEFB", fg="#0D47A1")
        self.btn_image.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_reprocess = create_flat_button(btn_frame1, "2. Refresh Line Art", self.generate_image_lineart, state=tk.DISABLED, bg="#E3F2FD", active_bg="#BBDEFB", fg="#0D47A1")
        self.btn_reprocess.pack(side="left", fill="x", expand=True, padx=(3, 0))
        Tooltip(self.btn_image, "Choose a source image to convert into line art.")
        Tooltip(self.btn_reprocess, "Re-generate line art from the current image with updated Detail/Thickness settings.")

        frame2 = ttk.LabelFrame(self.left_panel, text=" Mode B: Input Text ", padding=(10, 5))
        frame2.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 2))
        wrap2 = tk.Frame(frame2, bg=BG_COLOR)
        wrap2.pack(expand=True, fill="x")
        self.text_input = ttk.Entry(wrap2, font=(DEFAULT_FONT, 9))
        self.text_input.insert(0, "Enter text to draw...")
        self.text_input.pack(fill="x", pady=(0, 5))
        Tooltip(self.text_input, "Type the text you want drawn as line art.")
        font_frame = tk.Frame(wrap2, bg=BG_COLOR)
        font_frame.pack(fill="x", pady=2)
        lbl_font = tk.Label(font_frame, text="Font Style:", bg=BG_COLOR, font=(DEFAULT_FONT, 9))
        lbl_font.pack(side="left")
        self.font_combo = ttk.Combobox(font_frame, values=list(self.font_map.keys()), state="readonly", width=15, font=(DEFAULT_FONT, 9))
        self.font_combo.current(0)
        self.font_combo.pack(side="left", fill="x", expand=True, padx=5)
        Tooltip(lbl_font, "Choose a system font for text rendering.")
        Tooltip(self.font_combo, "Choose a system font for text rendering.")
        self.btn_text = create_flat_button(wrap2, "Generate Adaptive Text Line Art", self.process_text, bg="#FFF3E0", active_bg="#FFE0B2", fg="#E65100")
        self.btn_text.pack(fill="x", pady=(5, 0))
        Tooltip(self.btn_text, "Render the text above into line art using edge detection.")

        frame3 = ttk.LabelFrame(self.left_panel, text=" Mode C: Existing Line Art ", padding=(10, 5))
        frame3.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 2))
        wrap3 = tk.Frame(frame3, bg=BG_COLOR)
        wrap3.pack(expand=True, fill="x")
        self.btn_load_existing = create_flat_button(wrap3, "Open Saved Line Art", self.load_existing_lineart, bg="#F3E5F5", active_bg="#E1BEE7", fg="#4A148C")
        self.btn_load_existing.pack(fill="x")
        Tooltip(self.btn_load_existing, "Load a pre-made line art image directly, skipping edge detection.")

        frame_fog = ttk.LabelFrame(self.left_panel, text=" Mode D: Fog of War ", padding=(10, 5))
        frame_fog.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 2))
        wrap_fog = tk.Frame(frame_fog, bg=BG_COLOR)
        wrap_fog.pack(expand=True, fill="x")
        fog_conf_frame = tk.Frame(wrap_fog, bg=BG_COLOR)
        fog_conf_frame.pack(fill="x")
        lbl_gap = tk.Label(fog_conf_frame, text="Fill Gap:", bg=BG_COLOR, font=(DEFAULT_FONT, 9))
        lbl_gap.pack(side="left")
        self.fill_gap_slider = ttk.Scale(fog_conf_frame, from_=5, to=30, orient="horizontal", style="Green.Horizontal.TScale", command=self.on_fill_gap_change)
        self.fill_gap_slider.set(init_fill_gap)
        self.fill_gap_slider.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_gap_val = tk.Label(fog_conf_frame, text=f"{init_fill_gap} px", font=(DEFAULT_FONT, 10, "bold"), fg="#4CAF50", bg=BG_COLOR)
        self.lbl_gap_val.pack(side="left")
        Tooltip(lbl_gap, "Pixel spacing between fill strokes. Lower = denser fill, slower drawing.")
        Tooltip(self.fill_gap_slider, "Pixel spacing between fill strokes. Lower = denser fill, slower drawing.")
        self.btn_fill_fog = create_flat_button(wrap_fog, "Start Fog Sweep", lambda: self.start_digital_amber(mode="fill"), bg="#E8F5E9", active_bg="#B2DFDB", fg="#004D40")
        self.btn_fill_fog.pack(fill="x", pady=(5, 0))
        Tooltip(self.btn_fill_fog, "Fill a rectangular area with a crosshatch pattern. No image needed.")

        frame4 = ttk.LabelFrame(self.left_panel, text=" ⚙️ Global Drawing Settings ", padding=(10, 5))
        frame4.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 5))
        wrap4 = tk.Frame(frame4, bg=BG_COLOR)
        wrap4.pack(expand=True, fill="x")
        click_frame = tk.Frame(wrap4, bg=BG_COLOR)
        click_frame.pack(fill="x", pady=(0, 5))
        lbl_click = tk.Label(click_frame, text="Draw Button:", bg=BG_COLOR, font=(DEFAULT_FONT, 9))
        lbl_click.pack(side="left")
        self.toggle_switch = ToggleSwitch(click_frame, command=self.save_config)
        self.toggle_switch.set_state(init_is_left_click)
        self.toggle_switch.pack(side="left", padx=(10, 5))
        Tooltip(lbl_click, "Which mouse button to simulate. R = right-click (Slay the Spire 2), L = left-click (Paint).")
        Tooltip(self.toggle_switch, "Which mouse button to simulate. R = right-click (Slay the Spire 2), L = left-click (Paint).")
        speed_frame = tk.Frame(wrap4, bg=BG_COLOR)
        speed_frame.pack(fill="x")
        lbl_speed = tk.Label(speed_frame, text="Draw Speed:", bg=BG_COLOR, font=(DEFAULT_FONT, 9))
        lbl_speed.pack(side="left")
        self.speed_slider = ttk.Scale(speed_frame, from_=1, to=20, orient="horizontal", style="Blue.Horizontal.TScale", command=self.on_speed_change)
        self.speed_slider.set(init_speed)
        self.speed_slider.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_speed_val = tk.Label(speed_frame, text=str(init_speed), font=(DEFAULT_FONT, 10, "bold"), fg="#2196F3", bg=BG_COLOR)
        self.lbl_speed_val.pack(side="left")
        Tooltip(lbl_speed, "How many contour points to skip. Lower = smoother lines but slower. 2-4 recommended.")
        Tooltip(self.speed_slider, "How many contour points to skip. Lower = smoother lines but slower. 2-4 recommended.")

        # Right Side: Live Preview Panel
        self.preview = PreviewPanel(self.right_panel, on_image_loaded=self._on_preview_loaded)

        btn_action_frame = tk.Frame(self.right_panel, bg="white")
        btn_action_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.btn_open_folder = create_flat_button(btn_action_frame, "📁 Open Output Folder", self.open_output_folder, bg="#FFF8E1", active_bg="#FFECB3", fg="#FF8F00")
        self.btn_open_folder.pack(side="bottom", fill="x", pady=(10, 0))
        Tooltip(self.btn_open_folder, "Open the folder where generated line art images are saved.")

        btn_top_action = tk.Frame(btn_action_frame, bg="white")
        btn_top_action.pack(side="bottom", fill="x")

        self.btn_crop = create_flat_button(btn_top_action, "✂️ Crop", self.start_crop, state=tk.DISABLED, bg="#E0F2F1", active_bg="#B2DFDB", fg="#00695C")
        self.btn_crop.pack(side="left", fill="x", expand=True, padx=(0, 3))
        Tooltip(self.btn_crop, "Crop a region from the current line art.")

        self.btn_save_lineart = create_flat_button(btn_top_action, "💾 Save", self.save_current_lineart, state=tk.DISABLED, bg="#E8EAF6", active_bg="#C5CAE9", fg="#283593")
        self.btn_save_lineart.pack(side="left", fill="x", expand=True, padx=(3, 0))
        Tooltip(self.btn_save_lineart, "Save the current line art to a timestamped file.")

        self.root.deiconify()
        self.root.update()
        self.preview.show_hint()
        
        if self.is_first_run:
            self.root.after(TUTORIAL_POPUP_DELAY, self.show_first_run_tutorial)

    def update_status(self, msg):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert("1.0", msg)
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)

    def show_first_run_tutorial(self):
        tut = tk.Toplevel(self.root)
        tut.overrideredirect(True) 
        tut.attributes('-topmost', True)
        
        # UI components
        frame = tk.Frame(tut, bg="#FFFFFF", highlightbackground="#2196F3", highlightthickness=2)
        frame.pack(fill="both", expand=True)
        
        lbl_title = tk.Label(frame, text="✨ Welcome to Digital Amber Painter", font=(DEFAULT_FONT, 16, "bold"), bg="#FFFFFF", fg="#1976D2")
        lbl_title.pack(pady=(20, 10))

        lbl_desc = tk.Label(frame, text="To prevent stray brush strokes, please memorize these [Guardrail Hotkeys]:", font=(DEFAULT_FONT, 10), bg="#FFFFFF", fg=TEXT_LIGHT)
        lbl_desc.pack(pady=(0, 15))
        
        hk_frame = tk.Frame(frame, bg="#F9F9F9", bd=1, relief="solid")
        hk_frame.pack(padx=30, fill="x")
        
        tk.Label(hk_frame, text="P", font=(DEFAULT_FONT, 14, "bold"), bg="#F9F9F9", fg=ALERT_RED, width=12, anchor="e").grid(row=0, column=0, pady=10)
        tk.Label(hk_frame, text="Pause Drawing (auto pen-up)", font=(DEFAULT_FONT, 10), bg="#F9F9F9", fg=TEXT_COLOR, anchor="w").grid(row=0, column=1, sticky="w", padx=10)
        
        tk.Label(hk_frame, text="Ctrl + Alt + P", font=(DEFAULT_FONT, 14, "bold"), bg="#F9F9F9", fg="#4CAF50", width=12, anchor="e").grid(row=1, column=0, pady=10)
        tk.Label(hk_frame, text="Resume Drawing (memory breakpoint)", font=(DEFAULT_FONT, 10), bg="#F9F9F9", fg=TEXT_COLOR, anchor="w").grid(row=1, column=1, sticky="w", padx=10)
        
        tk.Label(hk_frame, text="[", font=(DEFAULT_FONT, 14, "bold"), bg="#F9F9F9", fg=ALERT_RED, width=12, anchor="e").grid(row=2, column=0, pady=10)
        tk.Label(hk_frame, text="Force Terminate (destroy task)", font=(DEFAULT_FONT, 10), bg="#F9F9F9", fg=TEXT_COLOR, anchor="w").grid(row=2, column=1, sticky="w", padx=10)

        # Added event=None for key binding compatibility
        def on_close(event=None):
            tut.destroy()
            self.is_first_run = False
            self.save_config()

        btn_ok = tk.Button(frame, text="Got it, let's start!", font=(DEFAULT_FONT, 11, "bold"), bg="#2196F3", fg="#FFFFFF", relief="flat", activebackground="#1976D2", activeforeground="#FFFFFF", command=on_close, cursor="hand2")
        btn_ok.pack(pady=(20, 20), ipadx=40, ipady=10)

        # --- Core fix area ---

        # Force UI layout calculation to get actual dimensions after DPI scaling
        tut.update_idletasks()
        actual_w = tut.winfo_reqwidth()
        actual_h = tut.winfo_reqheight()

        # Recalculate center position based on actual dimensions
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (actual_w // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (actual_h // 2)
        
        # Only set position, not fixed dimensions — let popup expand freely
        tut.geometry(f"+{x}+{y}")
        
        # Bind Esc key and force focus as fallback
        tut.bind("<Escape>", on_close)
        tut.focus_force()

    def on_closing(self):
        state.trigger_abort()
        time.sleep(0.1)  # Let drawing thread release mouse buttons
        self.root.destroy()

    def _on_preview_loaded(self):
        """Called by PreviewPanel when an image is successfully loaded."""
        self.btn_crop.config(state=tk.NORMAL)
        self.btn_save_lineart.config(state=tk.NORMAL)

    # ---------------------------------------------------------
    # Slider Anti-Deadloop and Snap Logic
    # ---------------------------------------------------------
    def on_detail_change(self, val):
        v = round(float(val))
        if abs(float(val) - v) > 0.001:  
            self.detail_slider.set(v)
        if hasattr(self, 'lbl_detail_val') and self.lbl_detail_val.cget("text") != str(v):
            self.lbl_detail_val.config(text=str(v))
            self.save_config()

    def on_speed_change(self, val):
        v = round(float(val))
        if abs(float(val) - v) > 0.001:
            self.speed_slider.set(v)
        if hasattr(self, 'lbl_speed_val') and self.lbl_speed_val.cget("text") != str(v):
            self.lbl_speed_val.config(text=str(v))
            self.save_config()
        
    def on_thickness_change(self, val):
        v = round(float(val))
        if abs(float(val) - v) > 0.001:
            self.thickness_slider.set(v)
        if hasattr(self, 'lbl_thick_val') and self.lbl_thick_val.cget("text") != str(v):
            self.lbl_thick_val.config(text=str(v))
            self.save_config()

    def on_fill_gap_change(self, val):
        v = round(float(val))
        if abs(float(val) - v) > 0.001:
            self.fill_gap_slider.set(v)
        if hasattr(self, 'lbl_gap_val') and self.lbl_gap_val.cget("text") != f"{v} px":
            self.lbl_gap_val.config(text=f"{v} px")
            self.save_config()

    # ---------------------------------------------------------
    # Config Save Logic
    # ---------------------------------------------------------
    def save_config(self, *args):
        if not hasattr(self, 'detail_slider') or not hasattr(self, 'speed_slider') or not hasattr(self, 'toggle_switch') or not hasattr(self, 'fill_gap_slider') or not hasattr(self, 'thickness_slider'):
            return
            
        is_top = self.topmost_var.get()
        self.root.attributes('-topmost', is_top) 
        
        self.app_config = AppConfig(
            topmost=is_top,
            detail=int(round(float(self.detail_slider.get()))),
            speed=int(round(float(self.speed_slider.get()))),
            fill_gap=int(round(float(self.fill_gap_slider.get()))),
            thickness=int(round(float(self.thickness_slider.get()))),
            is_left_click=self.toggle_switch.is_left_click,
            is_first_run=getattr(self, 'is_first_run', False),
        )
        save_config_file(self.config_path, self.app_config)

    # ---------------------------------------------------------
    # Save Line Art with Anti-Overwrite (Timestamp Naming)
    # ---------------------------------------------------------
    def save_current_lineart(self):
        if self.current_lineart_path and os.path.exists(self.current_lineart_path):
            # Human-readable timestamp
            time_str = time.strftime("%Y%m%d_%H%M%S")
            new_filename = f"saved_{time_str}.png"
            new_path = os.path.join(self.output_dir, new_filename)
            try:
                shutil.copy(self.current_lineart_path, new_path)
                self.current_lineart_path = new_path
                self.update_status(f"✅ Successfully saved:\n{new_filename}")
            except Exception as e:
                messagebox.showerror("Save Failed", f"Unable to save file: {e}")

    # --- Crop feature ---
    def start_crop(self):
        if self.current_lineart_path:
            CropOverlay(self.root, self.current_lineart_path, self.finish_crop)

    def finish_crop(self, new_cropped_path):
        self.current_lineart_path = new_cropped_path
        self.update_status(f"Cropped line art generated!\n{os.path.basename(new_cropped_path)}")
        self.preview.update(new_cropped_path)

    # --- Open folder ---
    def open_output_folder(self):
        try:
            os.startfile(os.path.abspath(self.output_dir))
        except Exception as e:
            messagebox.showerror("Error", f"Unable to open folder: {e}")

    # ---------------------------------------------------------
    # Guardrail: Any image-changing action aborts any running draw process
    # ---------------------------------------------------------
    def select_image(self):
        state.trigger_abort()
        file_path = filedialog.askopenfilename(title="Select Source Image", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        if file_path:
            self.last_raw_image_path = file_path
            self.btn_reprocess.config(state=tk.NORMAL)
            self.generate_image_lineart() 

    def generate_image_lineart(self):
        state.trigger_abort()
        if not self.last_raw_image_path: return

        detail = int(round(float(self.detail_slider.get())))
        thickness = int(round(float(self.thickness_slider.get())))
        save_path = generate_lineart(self.last_raw_image_path, detail, self.output_dir, thickness)

        self.current_lineart_path = save_path
        self.update_status(f"Image line art generated/refreshed!\nCurrent detail: {detail}")
        self.btn_start.config(state=tk.NORMAL)
        self.preview.update(save_path)

    def process_text(self):
        state.trigger_abort()
        text = self.text_input.get()
        if not text:
            messagebox.showwarning("Notice", "Please enter text first!")
            return

        selected_font_name = self.font_combo.get()
        actual_font_file = self.font_map.get(selected_font_name, "msyh.ttc")

        target_font_path, fallback_font_path = resolve_font(actual_font_file)
        final_font_path = target_font_path or fallback_font_path

        if not final_font_path:
            messagebox.showerror("Fatal Error", "No fonts found on your computer! Please check your system font library.")
            return

        if not target_font_path:
            messagebox.showinfo("Notice", f"Your system does not have [{selected_font_name}] installed.\nAutomatically substituted with [Microsoft YaHei].")

        try:
            thickness = int(round(float(self.thickness_slider.get())))
            save_path = generate_text_lineart(text, final_font_path, self.output_dir, thickness)
        except Exception as e:
            messagebox.showerror("Font Read Error", f"Font file may be corrupted:\n{e}")
            return

        self.current_lineart_path = save_path
        display_font = selected_font_name if target_font_path else "Microsoft YaHei (Fallback)"
        self.update_status(f"Adaptive text line art generated!\n{display_font}")
        self.btn_start.config(state=tk.NORMAL)
        self.preview.update(save_path)

    def load_existing_lineart(self):
        state.trigger_abort()
        initial_dir = os.path.abspath(self.output_dir)
        file_path = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="Select Saved Line Art",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")]
        )
        if file_path:
            self.current_lineart_path = file_path
            self.update_status(f"Line art loaded:\n{os.path.basename(file_path)}")
            self.btn_start.config(state=tk.NORMAL)
            self.preview.update(file_path)

    def start_digital_amber(self, mode="lineart"):
        state.trigger_abort()
        self.root.iconify()
        self.root.after(OVERLAY_LAUNCH_DELAY, lambda: self.launch_overlay(mode))

    def launch_overlay(self, mode):
        state.reset()
        
        current_step = int(round(float(self.speed_slider.get())))
        fill_gap = int(round(float(self.fill_gap_slider.get()))) if hasattr(self, 'fill_gap_slider') else DEFAULT_FILL_GAP
        is_left_click = self.toggle_switch.is_left_click
        
        DigitalAmberOverlay(self.root, self.current_lineart_path, 
                            lambda rx, ry, rw, rh, img_path, m: self.run_draw_thread(rx, ry, rw, rh, img_path, m, current_step, fill_gap, is_left_click), mode=mode)

    def run_draw_thread(self, rx, ry, rw, rh, img_path, mode, current_step, fill_gap, is_left_click):
        if mode == "fill":
            target = draw_fill
            args = (state, rx, ry, rw, rh, current_step, fill_gap, is_left_click)
        else:
            target = draw_contours
            args = (state, rx, ry, rw, rh, img_path, current_step, is_left_click)
        threading.Thread(target=target, args=args, daemon=True).start()

def main():
    root = tk.Tk()
    app = SpirePainterApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
