import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from spire_painter.constants import (
    BLUR_KERNEL_BASE, IMAGE_CANNY_LOWER_BASE, IMAGE_CANNY_UPPER_BASE,
    IMAGE_CANNY_DETAIL_FACTOR, TEXT_FONT_SIZE, TEXT_PADDING,
    TEXT_CANNY_LOW, TEXT_CANNY_HIGH,
)


def generate_lineart(image_path: str, detail: int, output_dir: str, thickness: int = 1) -> str:
    """Extract edges from an image and save as line art. Returns the saved path."""
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)

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
