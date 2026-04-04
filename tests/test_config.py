import json
import os
import tempfile

from spire_painter.config import AppConfig, load_config, save_config
from spire_painter.constants import DEFAULT_DETAIL, DEFAULT_SPEED, DEFAULT_FILL_GAP, DEFAULT_BRUSH_WIDTH


def test_defaults():
    cfg = AppConfig()
    assert cfg.detail == DEFAULT_DETAIL
    assert cfg.speed == DEFAULT_SPEED
    assert cfg.fill_gap == DEFAULT_FILL_GAP
    assert cfg.brush_width == DEFAULT_BRUSH_WIDTH
    assert cfg.thickness == 1
    assert cfg.draw_mode == "right"
    assert cfg.edge_close == 3
    assert cfg.is_first_run is True
    assert cfg.topmost is True


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.json")
        original = AppConfig(
            topmost=False, detail=8, speed=5, fill_gap=15,
            thickness=3, brush_width=5, draw_mode="middle",
            edge_close=5, is_first_run=False,
        )
        save_config(path, original)

        loaded = load_config(path)
        assert loaded.topmost == original.topmost
        assert loaded.detail == original.detail
        assert loaded.speed == original.speed
        assert loaded.fill_gap == original.fill_gap
        assert loaded.thickness == original.thickness
        assert loaded.brush_width == original.brush_width
        assert loaded.draw_mode == original.draw_mode
        assert loaded.edge_close == original.edge_close
        assert loaded.is_first_run == original.is_first_run


def test_load_missing_file_returns_defaults():
    cfg = load_config("/nonexistent/path/config.json")
    assert cfg.detail == DEFAULT_DETAIL
    assert cfg.is_first_run is True


def test_load_corrupted_file_returns_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.json")
        with open(path, "w") as f:
            f.write("{invalid json!!")
        cfg = load_config(path)
        assert cfg.detail == DEFAULT_DETAIL


def test_load_partial_config_fills_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.json")
        with open(path, "w") as f:
            json.dump({"detail": 9}, f)
        cfg = load_config(path)
        assert cfg.detail == 9
        assert cfg.speed == DEFAULT_SPEED
        assert cfg.brush_width == DEFAULT_BRUSH_WIDTH


def test_legacy_is_left_click_migration():
    """Old configs used is_left_click bool instead of draw_mode string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.json")
        with open(path, "w") as f:
            json.dump({"is_left_click": True}, f)
        cfg = load_config(path)
        assert cfg.draw_mode == "left"

        with open(path, "w") as f:
            json.dump({"is_left_click": False}, f)
        cfg = load_config(path)
        assert cfg.draw_mode == "right"


def test_legacy_click_mode_migration():
    """Very old configs used click_mode string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.json")
        with open(path, "w") as f:
            json.dump({"click_mode": "Left Click"}, f)
        cfg = load_config(path)
        assert cfg.draw_mode == "left"

        with open(path, "w") as f:
            json.dump({"click_mode": "Right Click"}, f)
        cfg = load_config(path)
        assert cfg.draw_mode == "right"
