# CLAUDE.md

## Project
Slay the Spire 2 auto-drawing tool. Tkinter GUI, Windows-only, uses ctypes mouse simulation and OpenCV edge detection.

## Structure
```
SlaytheSpire2Drawing.py    # entry point
spire_painter/
  constants.py             # all magic numbers, colors, fonts
  mouse.py                 # Windows ctypes mouse control
  drawing_state.py         # thread-safe pause/resume/abort state
  config.py                # JSON config dataclass + load/save
  image_processing.py      # Canny edge detection, text-to-lineart
  drawing_engine.py        # contour tracing + fog fill loops
  widgets.py               # DigitalAmberOverlay
  preview_panel.py         # zoomable/draggable preview canvas + inline crop
  ui/
    helpers.py             # flat_button, add_slider, snap_slider
    top_bar.py             # TopBar (status, hotkeys, always-on-top)
    image_source_panel.py  # ImageSourcePanel (detail, thickness, load buttons)
    drawing_settings_panel.py  # DrawingSettingsPanel (mode, speed, brush, edge close)
    preview_actions.py     # PreviewActions (crop, save, open folder)
    tutorial_popup.py      # show_tutorial()
  app.py                   # wires UI panels together + app logic
```

## Commands
```bash
# Run (requires admin for keyboard hooks)
python SlaytheSpire2Drawing.py

# Install deps
pip install opencv-python numpy Pillow keyboard

# Build exe
pyinstaller --onefile --noconsole --icon=brush.ico SlaytheSpire2Drawing.py
```

## Conventions
- All constants in `constants.py`, not scattered in code
- Thread-safe state via `DrawingState` class with `threading.Lock`, no bare globals
- Use specific exceptions (`except Exception`, `except OSError`), never bare `except:`
- UI text in English
- Widgets communicate via callbacks, not by reaching into parent state
