import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from spire_painter.constants import (
    BLUR_KERNEL_BASE, IMAGE_CANNY_LOWER_BASE, IMAGE_CANNY_UPPER_BASE,
    IMAGE_CANNY_DETAIL_FACTOR, TEXT_FONT_SIZE, TEXT_PADDING,
    TEXT_CANNY_LOW, TEXT_CANNY_HIGH, DEFAULT_BRUSH_WIDTH, EDGE_CLOSE_KERNEL,
)


def generate_lineart(image_path: str, detail: int, output_dir: str, thickness: int = 1) -> str:
    """Extract edges from an image and save as line art. Returns the saved path."""
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    k_size = int(max(1, (BLUR_KERNEL_BASE - detail) // 2 * 2 + 1))
    if k_size > 1:
        img = cv2.GaussianBlur(img, (k_size, k_size), 0)

    lower_thresh = int(IMAGE_CANNY_LOWER_BASE - detail * IMAGE_CANNY_DETAIL_FACTOR)
    upper_thresh = int(IMAGE_CANNY_UPPER_BASE - detail * IMAGE_CANNY_DETAIL_FACTOR)

    edges = cv2.Canny(img, lower_thresh, upper_thresh)

    if thickness > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thickness, thickness))
        edges = cv2.dilate(edges, kernel, iterations=1)

    inverted = cv2.bitwise_not(edges)

    save_path = os.path.join(output_dir, "last_image_lineart.png")
    cv2.imencode('.png', inverted)[1].tofile(save_path)
    return save_path


def simulate_drawing(lineart_path: str, speed: int, brush_width: int = DEFAULT_BRUSH_WIDTH,
                     edge_close: int = EDGE_CLOSE_KERNEL,
                     eraser_refine: bool = False) -> Image.Image:
    """Simulate what the drawing will look like given all parameters.

    Draws straight lines between consecutive sampled contour points — this
    matches what the game does. The game connects mouse positions with straight
    lines, so at high speeds curves become angular/geometric. Each contour is
    drawn independently (no lines between separate contours).
    """
    img = cv2.imdecode(np.fromfile(lineart_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return Image.open(lineart_path).convert("RGB")

    edges = cv2.bitwise_not(img)

    if edge_close > 1:
        close_kern = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (edge_close, edge_close)
        )
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, close_kern)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    # Draw straight lines between consecutive sampled points per contour.
    # At speed 1: points are 1px apart, so lines trace the original curve.
    # At high speeds: points are far apart, lines cut across curves = angular look.
    canvas = np.full_like(img, 255)
    for contour in contours:
        if len(contour) == 0:
            continue
        points = contour[::speed]
        if len(points) < 2:
            # Single point — just draw a dot
            if len(points) == 1:
                cv2.circle(canvas, tuple(points[0][0]), max(1, brush_width // 2), 0, -1)
            continue
        for i in range(len(points) - 1):
            pt1 = tuple(points[i][0])
            pt2 = tuple(points[i + 1][0])
            cv2.line(canvas, pt1, pt2, 0, brush_width)

    if eraser_refine and brush_width > 2:
        # Pass 2: Erase the excess (eraser is wider than pen, will overshoot)
        eraser_edges = compute_eraser_edges(edges, brush_width)
        eraser_contours, _ = cv2.findContours(eraser_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        # Eraser in StS2 is thicker than the pen — simulate that
        eraser_width = max(2, brush_width)
        for contour in eraser_contours:
            if len(contour) == 0:
                continue
            points = contour[::speed]
            if len(points) < 2:
                if len(points) == 1:
                    cv2.circle(canvas, tuple(points[0][0]), eraser_width // 2, 255, -1)
                continue
            for i in range(len(points) - 1):
                pt1 = tuple(points[i][0])
                pt2 = tuple(points[i + 1][0])
                cv2.line(canvas, pt1, pt2, 255, eraser_width)

        # Pass 3: Redraw original edges to restore detail the eraser ate
        for contour in contours:
            if len(contour) == 0:
                continue
            points = contour[::speed]
            if len(points) < 2:
                if len(points) == 1:
                    cv2.circle(canvas, tuple(points[0][0]), max(1, brush_width // 2), 0, -1)
                continue
            for i in range(len(points) - 1):
                pt1 = tuple(points[i][0])
                pt2 = tuple(points[i + 1][0])
                cv2.line(canvas, pt1, pt2, 0, brush_width)

    return Image.fromarray(canvas).convert("RGB")


def compute_eraser_edges(edges, brush_width):
    """Compute the excess pixels that the eraser should remove.

    The pen draws at `brush_width` pixels wide. The original edges are 1px.
    The excess is: dilated(edges, brush_width) minus dilated(edges, ~2px).
    This gives the outer ring of fat that the eraser should carve away,
    leaving a thin ~2px line behind.
    """
    if brush_width <= 2:
        return np.zeros_like(edges)

    # What the thick pen will draw
    pen_kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (brush_width, brush_width))
    thick = cv2.dilate(edges, pen_kern, iterations=1)

    # What we want to keep — the original edges slightly thickened so they
    # remain visible after erasing (a 1px line would be too fragile)
    keep_size = min(3, brush_width - 1)
    if keep_size > 1:
        keep_kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (keep_size, keep_size))
        kept = cv2.dilate(edges, keep_kern, iterations=1)
    else:
        kept = edges

    # The excess is the outer ring: thick minus what we keep
    excess = cv2.subtract(thick, kept)
    return excess


def simulate_drawing(lineart_path: str, speed: int, brush_width: int = DEFAULT_BRUSH_WIDTH,
                     edge_close: int = EDGE_CLOSE_KERNEL,
                     eraser_refine: bool = False) -> Image.Image:
    """Simulate what the drawing will look like given all parameters.

    When eraser_refine is True, simulates the two-pass process:
    1. Draw with thick brush (pen)
    2. Erase the excess to reveal thin lines
    """
    img = cv2.imdecode(np.fromfile(lineart_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return Image.open(lineart_path).convert("RGB")

    edges = cv2.bitwise_not(img)

    if edge_close > 1:
        close_kern = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (edge_close, edge_close)
        )
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, close_kern)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    # Pass 1: draw with thick brush
    canvas = np.full_like(img, 255)
    for contour in contours:
        if len(contour) == 0:
            continue
        points = contour[::speed]
        if len(points) < 2:
            continue
        for i in range(len(points) - 1):
            pt1 = tuple(points[i][0])
            pt2 = tuple(points[i + 1][0])
            cv2.line(canvas, pt1, pt2, 0, brush_width)

    if eraser_refine and brush_width > 1:
        # Pass 2: erase the excess
        # Compute what the eraser should remove
        eraser_edges = compute_eraser_edges(edges, brush_width)
        eraser_contours, _ = cv2.findContours(eraser_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

        for contour in eraser_contours:
            if len(contour) == 0:
                continue
            points = contour[::speed]
            if len(points) < 2:
                continue
            for i in range(len(points) - 1):
                pt1 = tuple(points[i][0])
                pt2 = tuple(points[i + 1][0])
                # Eraser draws white (removes ink)
                cv2.line(canvas, pt1, pt2, 255, max(1, brush_width // 2))

    return Image.fromarray(canvas).convert("RGB")


def resolve_font(font_file: str) -> tuple[str | None, str | None]:
    """Find the requested font file on the system. Returns (target_path, fallback_path)."""
    font_dirs = [
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts'),
    ]

    target_path = None
    fallback_path = None

    for d in font_dirs:
        test_path = os.path.join(d, font_file)
        if os.path.exists(test_path):
            target_path = test_path
            break

    if not target_path:
        for d in font_dirs:
            test_path = os.path.join(d, 'msyh.ttc')
            if os.path.exists(test_path):
                fallback_path = test_path
                break

    return target_path, fallback_path


def generate_text_lineart(text: str, font_path: str, output_dir: str, thickness: int = 1) -> str:
    """Render text as line art using edge detection. Returns the saved path."""
    fnt = ImageFont.truetype(font_path, TEXT_FONT_SIZE)

    dummy_img = Image.new('RGB', (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    bbox = dummy_draw.textbbox((0, 0), text, font=fnt)

    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    canvas_w = int(text_w + TEXT_PADDING * 2)
    canvas_h = int(text_h + TEXT_PADDING * 2)

    img = Image.new('RGB', (canvas_w, canvas_h), color='white')
    d = ImageDraw.Draw(img)

    draw_x = TEXT_PADDING - bbox[0]
    draw_y = TEXT_PADDING - bbox[1]
    d.text((draw_x, draw_y), text, font=fnt, fill='black')

    open_cv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(open_cv_image, TEXT_CANNY_LOW, TEXT_CANNY_HIGH)

    if thickness > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thickness, thickness))
        edges = cv2.dilate(edges, kernel, iterations=1)

    inverted = cv2.bitwise_not(edges)

    save_path = os.path.join(output_dir, "last_text_lineart.png")
    cv2.imencode('.png', inverted)[1].tofile(save_path)
    return save_path
