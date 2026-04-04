# Slay the Spire 2 - Digital Auto-Painter

Forked from [https://github.com/SKYFIRE5836/Slay-the-Spire-2-Drawing](Slay-the-Spire-2-Drawing)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

An auto-drawing tool for Slay the Spire 2. It freezes your screen, lets you select a target area, and then automatically draws line art into the game using simulated mouse strokes. Supports images, text, pre-made line art, and area fills.

---

## What's New

### v1.2.1 (Hotfix)
- Fixed tutorial popup getting cut off on high-DPI displays (125%, 150%, etc.). Added `Esc` to dismiss.
- Fixed `P` and `[` hotkeys firing during normal typing. They now only trigger while a drawing task is active.

### v1.2.0 (Major Update)
- **Multi-monitor support** — uses `VIRTUALDESK` so selection and drawing work correctly across screens.
- **Pause & resume** — press `P` to pause mid-draw, `Ctrl+Alt+P` to resume from where you left off, `[` to abort.
- **Zoomable preview** — scroll to zoom and drag to pan in the preview panel.
- **Left-click mode** — toggle between left and right mouse button for drawing. Includes a "Fog of War" fill mode.
- **Smooth strokes** — replaced the old pixel-by-pixel approach with continuous mouse drag, so lines work properly in Windows Paint and similar apps.

> See the [Releases page](../../releases) for older versions.

---

## Features

- **Screen freeze selection ("Digital Amber")** — dims all monitors and lets you draw a selection box over exactly where you want the art placed.
- **Physical mouse simulation** — holds the mouse button down and drags along contours rather than clicking individual pixels, producing smooth continuous lines.
- **Four drawing modes:**
  - **Mode A — Image to line art:** Loads an image and extracts edges using OpenCV (Gaussian blur + Canny edge detection).
  - **Mode B — Text to line art:** Renders text using a system font, then extracts the outlines.
  - **Mode C — Load existing line art:** Skips processing and draws a line art image directly.
  - **Mode D — Fog of War fill:** Fills a rectangular area with a crosshatch sweep pattern at a configurable spacing.
- **Safety hotkeys:**
  - `P` — Pause (releases the mouse immediately so you can interact with other windows).
  - `Ctrl + Alt + P` — Resume from the exact point where you paused.
  - `[` — Abort the current task entirely.
- **Modern UI** — 16:9 layout with a live preview panel, adjustable detail/speed sliders, and auto-saved settings.

---

## Quick Start

No Python needed — just grab the pre-built executable:

1. Download the latest `SlaytheSpire2Drawing.zip` from the [Releases page](../../releases).
2. Extract it anywhere. The folder should contain `SlaytheSpire2Drawing.exe` and an `output_lines` folder with `brush.ico`.
3. **Right-click the `.exe` and choose "Run as administrator."** This is required for the global hotkeys and mouse simulation to work.
4. Pick a drawing mode on the left, adjust detail and speed, then switch to your target app (the game, Paint, etc.).
5. Click **"Start Drawing"** — the screen dims and freezes.
6. Drag a rectangle over the area you want to draw in. Release the mouse and it starts automatically.

> **Tip:** Press `P` at any time to pause, or `[` to cancel.

---


## Developer Guide

### 1. Clone the repo

```bash
git clone https://github.com/lindenhutchinson/Slay-the-Spire-2-Drawing.git
cd Slay-the-Spire-2-Drawing
```

### 2. Install dependencies

Requires Python 3.8+:

```bash
pip install opencv-python numpy Pillow keyboard
```

The GUI uses Tkinter, which is included with Python.

### 3. Run it

The script uses global keyboard hooks, so your terminal needs admin privileges:

```bash
python SlaytheSpire2Drawing.py
```

### 4. Build an EXE

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --icon=brush.ico SlaytheSpire2Drawing.py
```

The output goes to the `dist` folder.

---

## FAQ

**The `.exe` doesn't launch, or pressing `P` doesn't pause.**
Run it as administrator. Windows blocks background keyboard hooks without elevated privileges.

**My antivirus flags or deletes it.**
The tool uses fullscreen capture, cross-monitor coordinate mapping, and global keyboard hooks — all of which trigger heuristic detections. It's also unsigned. The source code is fully available here; add it to your antivirus whitelist if you're comfortable.

**The lines come out jagged or polygonal.**
Your drawing speed is too high. Lower the speed slider (2-4 is a good range).

---

