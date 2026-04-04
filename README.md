# Slay the Spire 2 - Digital Auto-Painter

An automation tool for the "Digital Amber" drawing mechanic in Slay the Spire 2. This tool translates images, text, and custom line art into in-game mouse strokes with high precision.

---

## Quick Start (No Setup Required)

For most users, no Python installation is needed. Follow these steps to start drawing:

1. **Download:** Grab the latest SlaytheSpire2Drawing.exe from the [Releases](../../releases) page.
3. **Run as Admin:** Right-click SlaytheSpire2Drawing.exe and select "Run as Administrator". 
   > *Note: Admin rights are required for the tool to simulate mouse movements and listen for emergency stop hotkeys.*
4. **Select & Draw:**
   - Choose your mode (Image, Text, or Fill).
   - Click "Start Drawing"—your screen will dim and freeze.
   - Drag a box over the area in the game where you want to draw.
   - Release the mouse and the bot will begin.

### In-Game Controls
* **P**: Pause (immediately releases the mouse).
* **Ctrl + Alt + P**: Resume from where you paused.
* **[**: Abort the task entirely.

---

## Features

* **Image to Line Art:** Uses edge detection to trace any .png or .jpg directly onto the canvas.
* **Smooth Stroke Engine:** Simulates natural mouse dragging for continuous, high-quality lines compatible with the game's drawing engine.
* **Multi-Monitor Support:** Correctly handles coordinate mapping across different screen resolutions and "Virtual Desktop" setups.
* **Area Filling:** A "Fog of War" mode that fills a designated area with a configurable crosshatch pattern.
* **Adjustable Speed & Detail:** Fine-tune sliders to balance drawing quality with completion time.

---

## Developer & Technical Info

This repository is a refactored fork of the original [Slay-the-Spire-2-Drawing](https://github.com/SKYFIRE5836/Slay-the-Spire-2-Drawing) project. 

### Architecture
The project has been refactored into a modular package structure to separate concerns and improve maintainability:
* **SlaytheSpire2Drawing.py**: The entry point script that initializes the application.
* **spire_painter/**: The core logic package.
    * **app.py**: Manages the main application lifecycle and GUI coordination.
    * **image_processing.py**: Handles OpenCV-based edge detection and coordinate generation.
    * **drawing.py**: Contains the low-level mouse simulation and stroke logic.
* **output_lines/**: Contains required assets such as `brush.ico`.

### Running from Source
If you prefer to run the script manually, ensure you have Python 3.10+ installed:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python SlaytheSpire2Drawing.py
```

### Building the Executable
To package the app yourself using PyInstaller, ensure you include the required data directories:
```bash
python -m PyInstaller --onefile --noconsole --icon=output_lines/brush.ico SlaytheSpire2Drawing.py
```

---

## FAQ

**Why does my antivirus flag the .exe?**
The tool uses global keyboard hooks (for the Pause key) and simulates mouse input. Unsigned binaries performing these actions often trigger heuristic warnings. You can audit the source code in this repo and add an exclusion to your antivirus.

**The lines are jagged or shifting.**
Try lowering the Speed slider. If the drawing is offset, ensure your Windows "Scale and Layout" settings are consistent across monitors.
