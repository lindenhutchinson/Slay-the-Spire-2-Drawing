import json
from dataclasses import dataclass, asdict

from spire_painter.constants import DEFAULT_DETAIL, DEFAULT_SPEED, DEFAULT_FILL_GAP, DEFAULT_BRUSH_WIDTH, BLUR_KERNEL_BASE


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
    is_first_run: bool = True


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
            config.is_first_run = conf.get("is_first_run", config.is_first_run)
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
    except OSError:
        pass
