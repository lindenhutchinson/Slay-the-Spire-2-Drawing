import json
from dataclasses import dataclass, asdict

from spire_painter.constants import DEFAULT_DETAIL, DEFAULT_SPEED, DEFAULT_FILL_GAP


@dataclass
class AppConfig:
    topmost: bool = True
    detail: int = DEFAULT_DETAIL
    speed: int = DEFAULT_SPEED
    fill_gap: int = DEFAULT_FILL_GAP
    thickness: int = 1
    is_left_click: bool = False
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
            config.is_first_run = conf.get("is_first_run", config.is_first_run)
            if "is_left_click" in conf:
                config.is_left_click = conf["is_left_click"]
            elif "click_mode" in conf:
                config.is_left_click = "Left" in conf["click_mode"] or "\u5de6\u952e" in conf["click_mode"]
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
