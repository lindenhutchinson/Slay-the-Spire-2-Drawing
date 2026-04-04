import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from spire_painter.constants import (
    BLUR_KERNEL_BASE, IMAGE_CANNY_LOWER_BASE, IMAGE_CANNY_UPPER_BASE,
    IMAGE_CANNY_DETAIL_FACTOR, TEXT_FONT_SIZE, TEXT_PADDING,
    TEXT_CANNY_LOW, TEXT_CANNY_HIGH, DEFAULT_BRUSH_WIDTH, EDGE_CLOSE_KERNEL,
)


def remove_background(img):
    """Remove the dominant background from a grayscale image.

    Detects the most common pixel value (background), creates a mask of pixels
    close to it, and sets them to white. This prevents Canny from detecting
    edges at background texture/gradient boundaries.
    Returns the cleaned image.
    """
    # Find the dominant color via histogram peak
    hist = cv2.calcHist([img], [0], None, [256], [0, 256])
    bg_val = int(np.argmax(hist))

    # Pixels within this tolerance of the background are masked out
    tolerance = 30
    lower = max(0, bg_val - tolerance)
    upper = min(255, bg_val + tolerance)
    bg_mask = cv2.inRange(img, lower, upper)

    # Only remove if background covers a significant portion (>25%) of the image
    bg_ratio = np.count_nonzero(bg_mask) / bg_mask.size
    if bg_ratio < 0.25:
        return img

    result = img.copy()
    result[bg_mask > 0] = 255
    return result


def generate_lineart(image_path: str, detail: int, output_dir: str,
                     thickness: int = 1, blur: int = BLUR_KERNEL_BASE,
                     min_contour_len: int = 0, bg_removal: bool = False) -> str:
    """Extract edges from an image and save as line art. Returns the saved path."""
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    if bg_removal:
        img = remove_background(img)

    k_size = int(max(1, (blur - detail) // 2 * 2 + 1))
    if k_size > 1:
        img = cv2.GaussianBlur(img, (k_size, k_size), 0)

    lower_thresh = int(IMAGE_CANNY_LOWER_BASE - detail * IMAGE_CANNY_DETAIL_FACTOR)
    upper_thresh = int(IMAGE_CANNY_UPPER_BASE - detail * IMAGE_CANNY_DETAIL_FACTOR)

    edges = cv2.Canny(img, lower_thresh, upper_thresh)

    # Remove small noise contours before thickening
    if min_contour_len > 0:
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        mask = np.zeros_like(edges)
        for c in contours:
            if len(c) >= min_contour_len:
                cv2.drawContours(mask, [c], -1, 255, 1)
        edges = mask

    if thickness > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thickness, thickness))
        edges = cv2.dilate(edges, kernel, iterations=1)

    inverted = cv2.bitwise_not(edges)

    save_path = os.path.join(output_dir, "last_image_lineart.png")
    cv2.imencode('.png', inverted)[1].tofile(save_path)
    return save_path


def simulate_drawing(lineart_path: str, speed: int, brush_width: int = DEFAULT_BRUSH_WIDTH,
                     edge_close: int = EDGE_CLOSE_KERNEL,
                     eraser_refine: bool = False,
                     min_contour_len: int = 0) -> Image.Image:
    """Simulate what the drawing will look like given all parameters.

    Draws straight lines between consecutive sampled contour points — this
    matches what the game does. Each contour is drawn independently.
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

    canvas = np.full_like(img, 255)
    for contour in contours:
        if len(contour) < max(2, min_contour_len):
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
    """Compute the excess pixels that the eraser should remove."""
    if brush_width <= 2:
        return np.zeros_like(edges)

    pen_kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (brush_width, brush_width))
    thick = cv2.dilate(edges, pen_kern, iterations=1)

    keep_size = min(3, brush_width - 1)
    if keep_size > 1:
        keep_kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (keep_size, keep_size))
        kept = cv2.dilate(edges, keep_kern, iterations=1)
    else:
        kept = edges

    excess = cv2.subtract(thick, kept)
    return excess


def _get_canny(img, detail, blur):
    """Compute blurred + Canny edges. Separates the expensive step from edge_close."""
    k_size = int(max(1, (blur - detail) // 2 * 2 + 1))
    blurred = cv2.GaussianBlur(img, (k_size, k_size), 0) if k_size > 1 else img
    lower = int(IMAGE_CANNY_LOWER_BASE - detail * IMAGE_CANNY_DETAIL_FACTOR)
    upper = int(IMAGE_CANNY_UPPER_BASE - detail * IMAGE_CANNY_DETAIL_FACTOR)
    return cv2.Canny(blurred, lower, upper)


def _build_edges(img, detail, blur, edge_close, min_contour_len, canny_cache=None):
    """Run the full edge pipeline. Uses canny_cache dict to avoid recomputing blur+canny."""
    cache_key = (id(img), detail, blur)
    if canny_cache is not None and cache_key in canny_cache:
        edges = canny_cache[cache_key].copy()
    else:
        edges = _get_canny(img, detail, blur)
        if canny_cache is not None:
            canny_cache[cache_key] = edges.copy()

    if edge_close > 1:
        kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (edge_close, edge_close))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kern)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    if min_contour_len > 0:
        contours = [c for c in contours if len(c) >= min_contour_len]

    return contours


def _compute_gradient(img):
    """Compute gradient magnitude map for an image. Cached externally."""
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def _score_edges(contours, source_img=None, gradient=None):
    """Score how well contours represent the source image.

    When gradient is provided, measures edge coverage of high-gradient regions.
    Falls back to contour statistics if no gradient.
    """
    if not contours:
        return -1.0

    total = 0
    short = 0
    for c in contours:
        n = len(c)
        total += n
        if n < 5:
            short += 1

    if total == 0:
        return -1.0

    count = len(contours)
    noise_ratio = short / count

    if gradient is not None and source_img is not None:
        total_gradient = gradient.sum()
        if total_gradient < 1:
            return -1.0

        mask = np.zeros(source_img.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, contours, -1, 255, 1)

        edge_mask = mask > 0
        captured = gradient[edge_mask].sum()
        coverage = captured / total_gradient

        edge_pixels = np.count_nonzero(edge_mask)
        if edge_pixels > 0:
            precision = gradient[edge_mask].mean() / max(1.0, gradient.mean())
        else:
            precision = 0

        # Coverage is primary — capture as much real detail as possible.
        # Precision rewards edges landing on real gradients vs flat areas.
        # Drawing time is handled by the speed optimizer, not here.
        return (coverage * 60
                + min(precision, 3) * 10
                - noise_ratio * 10)
    else:
        avg_len = total / count
        return (min(avg_len, 500) * 0.1
                + total * 0.001
                - noise_ratio * 15)


def _measure_curvature(contours):
    """Precompute per-point curvature for all significant contours.

    Returns a single array of max deviations per segment at step=1 spacing,
    which can be quickly resampled for any speed. This avoids recomputing
    geometry for every candidate speed.
    """
    # Concatenate all significant contour points with separators
    all_pts = []
    contour_ranges = []  # (start, end) indices into all_pts
    for c in contours:
        if len(c) < 20:
            continue
        pts = c[:, 0, :].astype(np.float32)
        start = len(all_pts)
        all_pts.extend(pts)
        contour_ranges.append((start, len(all_pts)))

    if not all_pts:
        return None, []

    return np.array(all_pts, dtype=np.float32), contour_ranges


def _find_optimal_speed(contours, max_speed=10, max_deviation_px=1.5):
    """Find the highest draw speed where curves aren't distorted beyond threshold.

    Uses 90th percentile of max-deviation-per-segment to catch worst cases.
    """
    all_pts, ranges = _measure_curvature(contours)
    if all_pts is None:
        return 1

    best_speed = 1

    for speed in range(2, max_speed + 1):
        all_devs = []

        for start, end in ranges:
            pts = all_pts[start:end]
            n = len(pts)
            if n <= speed:
                continue

            starts_idx = np.arange(0, n - speed, speed)
            ends_idx = np.minimum(starts_idx + speed, n - 1)

            valid = (ends_idx - starts_idx) > 1
            starts_idx = starts_idx[valid]
            ends_idx = ends_idx[valid]

            if len(starts_idx) == 0:
                continue

            p1 = pts[starts_idx]
            p2 = pts[ends_idx]
            d = p2 - p1
            seg_len = np.hypot(d[:, 0], d[:, 1])

            short_mask = seg_len >= 0.5
            starts_idx = starts_idx[short_mask]
            ends_idx = ends_idx[short_mask]
            d = d[short_mask]
            seg_len = seg_len[short_mask]

            # For each segment, compute max deviation of skipped points
            for si in range(len(starts_idx)):
                s, e = starts_idx[si], ends_idx[si]
                intermediates = pts[s + 1:e] - p1[short_mask][si]
                cross = np.abs(d[si, 0] * intermediates[:, 1]
                               - d[si, 1] * intermediates[:, 0])
                all_devs.append(cross.max() / seg_len[si])

        if not all_devs:
            break

        p90 = np.percentile(all_devs, 90)
        if p90 <= max_deviation_px:
            best_speed = speed
        else:
            break

    return best_speed


def optimize_settings(image_path: str, output_dir: str, on_progress=None):
    """Find the fastest settings that produce acceptable drawing quality.

    Phase order matters — each phase depends on the previous:
    1. Edge detection (detail, blur, edge_close, bg_removal)
    2. Noise filtering (min_contour_len)
    3. Thickness (depends on final contour geometry)
    4. Speed (depends on final contour geometry after thickness)

    Args:
        on_progress: optional callback(fraction) called with 0.0-1.0 as work progresses.

    Returns a dict of the best settings found.
    """
    raw_img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if raw_img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    def _progress(frac):
        if on_progress:
            on_progress(frac)

    # Prepare image variants
    variants = [(False, raw_img)]
    cleaned = remove_background(raw_img)
    if not np.array_equal(cleaned, raw_img):
        variants.append((True, cleaned))

    # Precompute gradient maps once per variant (expensive, do it once)
    gradients = {}
    for _, img in variants:
        gradients[id(img)] = _compute_gradient(img)

    cache = {}

    # --- Phase 1: Coarse edge sweep (30%) ---
    combos = []
    for use_bg, img in variants:
        for detail in range(2, 10, 2):
            for blur in (3, 7, 11, 15):
                for edge_close in (1, 3, 5):
                    combos.append((use_bg, img, detail, blur, edge_close))

    results = []
    total = len(combos)
    for i, (use_bg, img, detail, blur, edge_close) in enumerate(combos):
        if i % 6 == 0:
            _progress(0.25 * (i / total))
        contours = _build_edges(img, detail, blur, edge_close, 0, cache)
        if not contours:
            continue
        score = _score_edges(contours, img, gradients[id(img)])
        results.append((score, use_bg, img, detail, blur, edge_close))

    if not results:
        _progress(1.0)
        return {}

    results.sort(key=lambda x: x[0], reverse=True)

    # --- Phase 2: Fine sweep around top 5 (25%) ---
    fine_seen = set()
    fine_combos = []
    for _, use_bg, img, detail, blur, edge_close in results[:5]:
        for d in range(max(1, detail - 1), min(11, detail + 2)):
            for b in (max(1, blur - 2), blur, blur + 2):
                if b > 1 and b % 2 == 0:
                    b += 1
                for ec in (max(1, edge_close - 2), edge_close, min(9, edge_close + 2)):
                    if ec > 1 and ec % 2 == 0:
                        ec += 1
                    key = (id(img), d, b, ec)
                    if key not in fine_seen:
                        fine_seen.add(key)
                        fine_combos.append((use_bg, img, d, b, ec))

    fine_results = []
    fine_total = len(fine_combos)
    for i, (use_bg, img, detail, blur, edge_close) in enumerate(fine_combos):
        if i % 4 == 0:
            _progress(0.25 + 0.25 * (i / max(1, fine_total)))
        contours = _build_edges(img, detail, blur, edge_close, 0, cache)
        if not contours:
            continue
        score = _score_edges(contours, img, gradients[id(img)])
        fine_results.append((score, use_bg, img, detail, blur, edge_close))

    all_results = results + fine_results
    all_results.sort(key=lambda x: x[0], reverse=True)
    _, use_bg, img, detail, blur, edge_close = all_results[0]

    _progress(0.55)

    # --- Phase 3: Noise filtering (5%) ---
    contours = _build_edges(img, detail, blur, edge_close, 0, cache)
    grad = gradients[id(img)]

    lengths = [len(c) for c in contours]
    short_ratio = sum(1 for l in lengths if l < 5) / max(1, len(lengths))

    best_min_len = 0
    if short_ratio > 0.3:
        base_score = _score_edges(contours, img, grad)
        for min_len in (4, 6):
            filtered = _build_edges(img, detail, blur, edge_close, min_len, cache)
            if filtered:
                s = _score_edges(filtered, img, grad)
                if s > base_score:
                    base_score = s
                    best_min_len = min_len

    # Get final contours after filtering
    contours = _build_edges(img, detail, blur, edge_close, best_min_len, cache)

    _progress(0.6)

    # --- Phase 4: Thickness (15%) ---
    # Get the edge map for the winning combo from cache
    cache_key = (id(img), detail, blur)
    if cache_key in cache:
        canny = cache[cache_key].copy()
    else:
        canny = _get_canny(img, detail, blur)
    if edge_close > 1:
        kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (edge_close, edge_close))
        canny = cv2.morphologyEx(canny, cv2.MORPH_CLOSE, kern)

    thin_contours, _ = cv2.findContours(canny, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    thin_count = len(thin_contours)
    thin_px = np.count_nonzero(canny)

    best_thickness = 1
    best_t_score = 0.0

    for t in (1, 2, 3):
        if t > 1:
            tk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (t, t))
            thick = cv2.dilate(canny, tk, iterations=1)
        else:
            thick = canny

        thick_px = np.count_nonzero(thick)
        expansion = thick_px / max(1, thin_px)

        thick_contours, _ = cv2.findContours(thick, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        thick_count = len(thick_contours)
        merge_ratio = thick_count / max(1, thin_count)

        score = (merge_ratio * 50 - expansion * 5 + (t - 1) * 2)

        if t == 1 or score > best_t_score:
            best_t_score = score
            best_thickness = t

    _progress(0.75)

    # --- Phase 5: Speed (25%) ---
    # Use the final contour geometry (after thickness choice) for speed analysis.
    # If thickness > 1, re-extract contours from the thickened edges.
    if best_thickness > 1:
        tk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (best_thickness, best_thickness))
        final_edges = cv2.dilate(canny, tk, iterations=1)
        final_contours, _ = cv2.findContours(final_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        if best_min_len > 0:
            final_contours = [c for c in final_contours if len(c) >= best_min_len]
    else:
        final_contours = contours

    best_speed = _find_optimal_speed(final_contours)

    _progress(1.0)

    return {
        'detail': detail,
        'blur': blur,
        'edge_close': edge_close,
        'min_contour_len': best_min_len,
        'thickness': best_thickness,
        'bg_removal': use_bg,
        'speed': best_speed,
    }


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
