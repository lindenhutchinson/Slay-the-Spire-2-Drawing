import json
import logging
import os
from dataclasses import dataclass, asdict

from spire_painter.constants import (
    DEFAULT_DETAIL, DEFAULT_SPEED, DEFAULT_FILL_GAP, DEFAULT_BRUSH_WIDTH,
    BLUR_KERNEL_BASE, DEFAULT_ERASER_WIDTH, PRESET_DIR_NAME,
)

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    topmost: bool = True
    detail: int = DEFAULT_DETAIL
    speed: int = DEFAULT_SPEED
    fill_gap: int = DEFAULT_FILL_GAP
    thickness: int = 1
    brush_width: int = DEFAULT_BRUSH_WIDTH
    blur: int = BLUR_KERNEL_BASE
    min_contour_len: int = 0
    bg_removal: bool = False
    draw_mode: str = "right"
    edge_close: int = 3
    eraser_refine: bool = False
    eraser_width: int = DEFAULT_ERASER_WIDTH
    is_first_run: bool = True
    # New features
    clahe_clip: float = 0.0       # 0 = disabled
    bezier_fitting: bool = False
    hatching_enabled: bool = False
    hatching_density: int = 4
    multi_resolution: bool = False


def load_config(path: str) -> AppConfig:
    """Load config from JSON file, returning defaults on any error."""
    config = AppConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            conf = json.load(f)
            config.topmost = conf.get("topmost", config.topmost)
            config.detail = conf.get("detail", config.detail)
            config.speed = conf.get("speed", config.speed)
            config.fill_gap = conf.get("fill_gap", config.fill_gap)
            config.thickness = conf.get("thickness", config.thickness)
            config.brush_width = conf.get("brush_width", config.brush_width)
            config.blur = conf.get("blur", config.blur)
            config.min_contour_len = conf.get("min_contour_len", config.min_contour_len)
            config.bg_removal = conf.get("bg_removal", config.bg_removal)
            config.edge_close = conf.get("edge_close", config.edge_close)
            config.eraser_refine = conf.get("eraser_refine", config.eraser_refine)
            config.eraser_width = conf.get("eraser_width", config.eraser_width)
            config.is_first_run = conf.get("is_first_run", config.is_first_run)
            config.clahe_clip = conf.get("clahe_clip", config.clahe_clip)
            config.bezier_fitting = conf.get("bezier_fitting", config.bezier_fitting)
            config.hatching_enabled = conf.get("hatching_enabled", config.hatching_enabled)
            config.hatching_density = conf.get("hatching_density", config.hatching_density)
            config.multi_resolution = conf.get("multi_resolution", config.multi_resolution)
            # draw_mode: new field, with migration from legacy is_left_click
            if "draw_mode" in conf:
                config.draw_mode = conf["draw_mode"]
            elif "is_left_click" in conf:
                config.draw_mode = "left" if conf["is_left_click"] else "right"
            elif "click_mode" in conf:
                config.draw_mode = "left" if ("Left" in conf["click_mode"] or "\u5de6\u952e" in conf["click_mode"]) else "right"
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    return config


def save_config(path: str, config: AppConfig):
    """Save config to JSON file."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(config), f)
    except OSError as e:
        logger.warning("Failed to save config: %s", e)


# ---------------------------------------------------------
# Preset profiles
# ---------------------------------------------------------

# Fields to exclude from presets (UI-only state, not drawing parameters)
_PRESET_EXCLUDE = {"topmost", "is_first_run"}


def _presets_dir(output_dir: str) -> str:
    d = os.path.join(output_dir, PRESET_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def list_presets(output_dir: str) -> list[str]:
    """Return sorted list of preset names."""
    d = _presets_dir(output_dir)
    names = []
    for f in os.listdir(d):
        if f.endswith(".json"):
            names.append(f[:-5])
    names.sort()
    return names


def save_preset(output_dir: str, name: str, config: AppConfig):
    """Save a named preset."""
    d = _presets_dir(output_dir)
    data = {k: v for k, v in asdict(config).items() if k not in _PRESET_EXCLUDE}
    path = os.path.join(d, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_preset(output_dir: str, name: str) -> dict:
    """Load a named preset. Returns a dict of settings."""
    d = _presets_dir(output_dir)
    path = os.path.join(d, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_preset(output_dir: str, name: str):
    """Delete a named preset."""
    d = _presets_dir(output_dir)
    path = os.path.join(d, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)
