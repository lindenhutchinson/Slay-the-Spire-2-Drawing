import os
import tempfile

import cv2
import numpy as np
from PIL import Image

from spire_painter.image_processing import (
    generate_lineart, generate_text_lineart, simulate_drawing, resolve_font,
)


def _create_test_image(tmpdir, width=100, height=100):
    """Create a simple test image with a black square on white background."""
    img = np.full((height, width), 255, dtype=np.uint8)
    img[30:70, 30:70] = 0  # black square
    path = os.path.join(tmpdir, "test_input.png")
    cv2.imencode('.png', img)[1].tofile(path)
    return path


class TestGenerateLineart:
    def test_produces_output_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = _create_test_image(tmpdir)
            result = generate_lineart(src, detail=5, output_dir=tmpdir)
            assert os.path.exists(result)
            assert result.endswith(".png")

    def test_output_is_valid_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = _create_test_image(tmpdir)
            result = generate_lineart(src, detail=5, output_dir=tmpdir)
            img = cv2.imdecode(np.fromfile(result, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            assert img is not None
            assert img.shape == (100, 100)

    def test_detail_affects_output(self):
        """Higher detail should produce more edges (more non-white pixels)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = _create_test_image(tmpdir)
            low = generate_lineart(src, detail=1, output_dir=tmpdir)
            low_img = cv2.imdecode(np.fromfile(low, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            low_dark = np.sum(low_img < 128)

            high = generate_lineart(src, detail=10, output_dir=tmpdir)
            high_img = cv2.imdecode(np.fromfile(high, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            high_dark = np.sum(high_img < 128)

            assert high_dark >= low_dark

    def test_thickness_affects_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = _create_test_image(tmpdir)
            thin = generate_lineart(src, detail=5, output_dir=tmpdir, thickness=1)
            thin_img = cv2.imdecode(np.fromfile(thin, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            thin_dark = np.sum(thin_img < 128)

            thick = generate_lineart(src, detail=5, output_dir=tmpdir, thickness=5)
            thick_img = cv2.imdecode(np.fromfile(thick, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            thick_dark = np.sum(thick_img < 128)

            assert thick_dark >= thin_dark

    def test_raises_on_invalid_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = os.path.join(tmpdir, "empty.png")
            with open(bad_path, "wb") as f:
                f.write(b"not an image")
            try:
                generate_lineart(bad_path, detail=5, output_dir=tmpdir)
                assert False, "Should have raised"
            except ValueError:
                pass


class TestSimulateDrawing:
    def test_returns_pil_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = _create_test_image(tmpdir)
            result_path = generate_lineart(src, detail=5, output_dir=tmpdir)
            sim = simulate_drawing(result_path, speed=1, brush_width=3)
            assert isinstance(sim, Image.Image)
            assert sim.mode == "RGB"

    def test_speed_produces_different_output(self):
        """Different speed values should produce different pixel counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a larger image with a circle so there are many contour points
            img = np.full((300, 300), 255, dtype=np.uint8)
            cv2.circle(img, (150, 150), 100, 0, 2)
            cv2.circle(img, (150, 150), 50, 0, 2)
            path = os.path.join(tmpdir, "circles.png")
            cv2.imencode('.png', img)[1].tofile(path)
            result_path = generate_lineart(path, detail=8, output_dir=tmpdir)

            slow = simulate_drawing(result_path, speed=1, brush_width=1)
            fast = simulate_drawing(result_path, speed=15, brush_width=1)

            slow_arr = np.array(slow.convert("L"))
            fast_arr = np.array(fast.convert("L"))
            slow_dark = np.sum(slow_arr < 128)
            fast_dark = np.sum(fast_arr < 128)

            # They should differ — speed changes the drawn output
            assert slow_dark != fast_dark

    def test_brush_width_affects_thickness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = _create_test_image(tmpdir)
            result_path = generate_lineart(src, detail=5, output_dir=tmpdir)

            thin = simulate_drawing(result_path, speed=1, brush_width=1)
            thick = simulate_drawing(result_path, speed=1, brush_width=5)

            thin_arr = np.array(thin.convert("L"))
            thick_arr = np.array(thick.convert("L"))
            thin_dark = np.sum(thin_arr < 128)
            thick_dark = np.sum(thick_arr < 128)

            assert thick_dark >= thin_dark


class TestResolveFont:
    def test_returns_tuple(self):
        target, fallback = resolve_font("msyh.ttc")
        assert isinstance(target, (str, type(None)))
        assert isinstance(fallback, (str, type(None)))

    def test_nonexistent_font_falls_back(self):
        target, fallback = resolve_font("definitely_not_a_font_12345.ttf")
        assert target is None
        # Fallback may or may not exist depending on system
