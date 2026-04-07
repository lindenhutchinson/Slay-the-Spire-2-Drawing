import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from spire_painter.constants import (
    BLUR_KERNEL_BASE, IMAGE_CANNY_LOWER_BASE, IMAGE_CANNY_UPPER_BASE,
    IMAGE_CANNY_DETAIL_FACTOR, TEXT_FONT_SIZE, TEXT_PADDING,
    TEXT_CANNY_LOW, TEXT_CANNY_HIGH, DEFAULT_BRUSH_WIDTH, EDGE_CLOSE_KERNEL,
    BILATERAL_D, BILATERAL_SIGMA_BASE, CANNY_SIGMA_BASE, CLAHE_GRID_SIZE,
    HATCHING_LEVELS, HATCHING_MIN_GAP, HATCHING_MAX_GAP, BEZIER_MAX_ERROR,
)


# ---------------------------------------------------------
# Preprocessing helpers
# ---------------------------------------------------------

def remove_background(img):
    """Remove the dominant background from a grayscale image.

    Detects the most common pixel value (background), creates a mask of pixels
    close to it, and sets them to white. This prevents Canny from detecting
    edges at background texture/gradient boundaries.
    Returns the cleaned image.
    """
    hist = cv2.calcHist([img], [0], None, [256], [0, 256])
    bg_val = int(np.argmax(hist))

    tolerance = 30
    lower = max(0, bg_val - tolerance)
    upper = min(255, bg_val + tolerance)
    bg_mask = cv2.inRange(img, lower, upper)

    bg_ratio = np.count_nonzero(bg_mask) / bg_mask.size
    if bg_ratio < 0.25:
        return img

    result = img.copy()
    result[bg_mask > 0] = 255
    return result


def _apply_clahe(img, clip_limit):
    """Apply CLAHE contrast enhancement. Returns original if clip_limit <= 0."""
    if clip_limit <= 0:
        return img
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(CLAHE_GRID_SIZE, CLAHE_GRID_SIZE))
    return clahe.apply(img)


def _apply_bilateral(img, blur):
    """Apply bilateral filter (edge-preserving denoising) instead of Gaussian blur."""
    if blur <= 1:
        return img
    sigma = blur * BILATERAL_SIGMA_BASE
    return cv2.bilateralFilter(img, d=BILATERAL_D, sigmaColor=sigma, sigmaSpace=sigma)


def _adaptive_canny_thresholds(img, detail):
    """Compute adaptive Canny thresholds based on image median.

    detail slider (1-10) adjusts sensitivity around the adaptive base.
    Higher detail = tighter sigma = more edges captured.
    """
    median = float(np.median(img))
    # detail=10 -> sigma=0.33 (tight, many edges), detail=1 -> sigma=0.78 (loose, fewer edges)
    sigma = CANNY_SIGMA_BASE + (10 - detail) * 0.05
    lower = int(max(0, (1.0 - sigma) * median))
    upper = int(min(255, (1.0 + sigma) * median))
    return lower, upper


# ---------------------------------------------------------
# Bezier curve fitting
# ---------------------------------------------------------

def _bezier_point(p0, p1, p2, p3, t):
    """Evaluate cubic bezier at parameter t."""
    u = 1.0 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3


def _fit_bezier_segment(points):
    """Fit a single cubic bezier to a sequence of 2D points.

    Uses simple chord-length parameterization with least-squares.
    Returns (p0, p1, p2, p3) control points.
    """
    pts = np.array(points, dtype=np.float64)
    n = len(pts)
    if n < 2:
        return pts[0], pts[0], pts[0], pts[0]
    if n == 2:
        return pts[0], pts[0], pts[1], pts[1]

    # Chord-length parameterization
    dists = np.sqrt(np.sum(np.diff(pts, axis=0)**2, axis=1))
    total = dists.sum()
    if total < 1e-6:
        return pts[0], pts[0], pts[-1], pts[-1]
    t_vals = np.zeros(n)
    t_vals[1:] = np.cumsum(dists) / total

    p0 = pts[0]
    p3 = pts[-1]

    # Build system for control points p1, p2
    A = np.zeros((n, 2))
    for i in range(n):
        t = t_vals[i]
        u = 1 - t
        A[i, 0] = 3 * u**2 * t
        A[i, 1] = 3 * u * t**2

    rhs = pts.copy()
    for i in range(n):
        t = t_vals[i]
        u = 1 - t
        rhs[i] -= u**3 * p0 + t**3 * p3

    # Solve least squares for each coordinate
    AtA = A.T @ A
    if np.linalg.det(AtA) < 1e-10:
        # Degenerate — use simple thirds
        p1 = p0 + (p3 - p0) / 3
        p2 = p0 + 2 * (p3 - p0) / 3
        return p0, p1, p2, p3

    AtB = A.T @ rhs
    sol = np.linalg.solve(AtA, AtB)
    p1 = sol[0]
    p2 = sol[1]

    return p0, p1, p2, p3


def _bezier_max_error(points, p0, p1, p2, p3):
    """Compute max distance between original points and bezier curve."""
    pts = np.array(points, dtype=np.float64)
    n = len(pts)
    if n < 2:
        return 0.0
    dists = np.sqrt(np.sum(np.diff(pts, axis=0)**2, axis=1))
    total = dists.sum()
    if total < 1e-6:
        return 0.0
    t_vals = np.zeros(n)
    t_vals[1:] = np.cumsum(dists) / total

    max_err = 0.0
    for i in range(n):
        bp = _bezier_point(p0, p1, p2, p3, t_vals[i])
        err = np.sqrt(np.sum((pts[i] - bp)**2))
        if err > max_err:
            max_err = err
    return max_err


def fit_bezier_contour(screen_pts, max_error=BEZIER_MAX_ERROR):
    """Fit cubic bezier curves to a list of (x,y) points.

    Adaptively subdivides until error is within threshold.
    Returns a list of smooth points evaluated from the bezier curves.
    """
    if len(screen_pts) < 3:
        return screen_pts

    # Use approxPolyDP to find split points
    pts_arr = np.array(screen_pts, dtype=np.float32).reshape(-1, 1, 2)
    epsilon = max_error * 0.5
    simplified = cv2.approxPolyDP(pts_arr, epsilon, closed=False)
    split_indices = []
    for sp in simplified[:, 0, :]:
        # Find nearest original point
        dists = np.sum((np.array(screen_pts, dtype=np.float32) - sp)**2, axis=1)
        split_indices.append(int(np.argmin(dists)))
    split_indices = sorted(set(split_indices))
    if split_indices[0] != 0:
        split_indices.insert(0, 0)
    if split_indices[-1] != len(screen_pts) - 1:
        split_indices.append(len(screen_pts) - 1)

    result = []
    for seg_i in range(len(split_indices) - 1):
        start = split_indices[seg_i]
        end = split_indices[seg_i + 1]
        segment = screen_pts[start:end + 1]

        if len(segment) < 2:
            if segment:
                result.append(segment[0])
            continue

        p0, p1, p2, p3 = _fit_bezier_segment(segment)

        # Evaluate bezier at uniform intervals based on arc length
        arc_len = sum(
            ((segment[i+1][0] - segment[i][0])**2 + (segment[i+1][1] - segment[i][1])**2)**0.5
            for i in range(len(segment) - 1)
        )
        num_points = max(2, int(arc_len / 2))  # ~1 point per 2 pixels

        for j in range(num_points):
            t = j / (num_points - 1) if num_points > 1 else 0
            bp = _bezier_point(p0, p1, p2, p3, t)
            result.append((int(round(bp[0])), int(round(bp[1]))))

    # Deduplicate consecutive points
    if not result:
        return screen_pts
    deduped = [result[0]]
    for p in result[1:]:
        if p != deduped[-1]:
            deduped.append(p)
    return deduped


# ---------------------------------------------------------
# Hatching / shading
# ---------------------------------------------------------

def generate_hatching(gray_img, levels=HATCHING_LEVELS, min_gap=HATCHING_MIN_GAP,
                      max_gap=HATCHING_MAX_GAP):
    """Generate hatching lines from a grayscale image for shading.

    Quantizes the image into brightness levels and generates parallel lines
    at different angles and densities for darker regions.

    Returns a list of contour-like arrays compatible with _contours_to_strokes.
    """
    h, w = gray_img.shape[:2]
    if levels < 1:
        return []

    # Quantize into levels (0 = darkest, levels-1 = lightest)
    # We skip the lightest level (no hatching for white areas)
    thresholds = np.linspace(0, 255, levels + 1)
    hatching_contours = []

    for level in range(levels - 1):  # skip lightest
        lo = thresholds[level]
        hi = thresholds[level + 1]

        # Create mask for this brightness band
        mask = ((gray_img >= lo) & (gray_img < hi)).astype(np.uint8) * 255

        # Morphological clean-up to remove tiny regions
        kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kern)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kern)

        if np.count_nonzero(mask) < 50:
            continue

        # Darker levels get denser hatching and different angles
        darkness = 1.0 - (level / max(1, levels - 1))
        gap = int(max_gap - darkness * (max_gap - min_gap))
        gap = max(min_gap, gap)

        # Angle varies by level: 45, 135, 90, 0 degrees
        angles = [45, 135, 90, 0]
        angle = angles[level % len(angles)]

        # Generate parallel lines at the given angle, clipped to mask
        lines = _generate_parallel_lines(w, h, angle, gap, mask)
        hatching_contours.extend(lines)

    return hatching_contours


def _generate_parallel_lines(w, h, angle_deg, gap, mask):
    """Generate parallel lines at a given angle, clipped to a binary mask.

    Returns list of contour-like numpy arrays (Nx1x2 int32).
    """
    angle_rad = np.radians(angle_deg)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    # Direction along the line
    dx, dy = cos_a, sin_a
    # Direction perpendicular to the line (for spacing)
    nx, ny = -sin_a, cos_a

    # Compute how many lines we need
    diag = int(np.sqrt(w**2 + h**2))
    cx, cy = w / 2, h / 2

    contours = []
    num_lines = diag // max(1, gap)

    for i in range(-num_lines // 2, num_lines // 2 + 1):
        # Line center offset perpendicular to line direction
        ox = cx + nx * i * gap
        oy = cy + ny * i * gap

        # Line endpoints (extend beyond image bounds)
        x1 = int(ox - dx * diag)
        y1 = int(oy - dy * diag)
        x2 = int(ox + dx * diag)
        y2 = int(oy + dy * diag)

        # Rasterize the line and clip to mask
        line_img = np.zeros((h, w), dtype=np.uint8)
        cv2.line(line_img, (x1, y1), (x2, y2), 255, 1)
        clipped = cv2.bitwise_and(line_img, mask)

        # Extract connected segments from the clipped line
        line_contours, _ = cv2.findContours(clipped, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for c in line_contours:
            if len(c) >= 3:
                contours.append(c)

    return contours


# ---------------------------------------------------------
# Line art generation
# ---------------------------------------------------------

def generate_lineart(image_path: str, detail: int, output_dir: str,
                     thickness: int = 1, blur: int = BLUR_KERNEL_BASE,
                     min_contour_len: int = 0, bg_removal: bool = False,
                     clahe_clip: float = 0.0) -> str:
    """Extract edges from an image and save as line art. Returns the saved path."""
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    if bg_removal:
        img = remove_background(img)

    img = _apply_clahe(img, clahe_clip)
    img = _apply_bilateral(img, blur)

    lower_thresh, upper_thresh = _adaptive_canny_thresholds(img, detail)
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
                     min_contour_len: int = 0,
                     bezier_fitting: bool = False,
                     hatching_enabled: bool = False,
                     hatching_density: int = HATCHING_LEVELS,
                     source_gray: np.ndarray | None = None) -> Image.Image:
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

    # Draw edge contours
    for contour in contours:
        if len(contour) < max(2, min_contour_len):
            continue
        points = contour[::speed]
        if len(points) < 2:
            if len(points) == 1:
                cv2.circle(canvas, tuple(points[0][0]), max(1, brush_width // 2), 0, -1)
            continue

        if bezier_fitting and len(points) >= 3:
            screen_pts = [tuple(p[0]) for p in points]
            smooth_pts = fit_bezier_contour(screen_pts)
            for i in range(len(smooth_pts) - 1):
                cv2.line(canvas, smooth_pts[i], smooth_pts[i + 1], 0, brush_width)
        else:
            for i in range(len(points) - 1):
                pt1 = tuple(points[i][0])
                pt2 = tuple(points[i + 1][0])
                cv2.line(canvas, pt1, pt2, 0, brush_width)

    # Draw hatching if enabled
    if hatching_enabled and source_gray is not None:
        hatch_contours = generate_hatching(source_gray, levels=hatching_density)
        for contour in hatch_contours:
            points = contour[::max(1, speed)]
            if len(points) < 2:
                continue
            for i in range(len(points) - 1):
                pt1 = tuple(points[i][0])
                pt2 = tuple(points[i + 1][0])
                cv2.line(canvas, pt1, pt2, 0, max(1, brush_width // 2))

    return Image.fromarray(canvas).convert("RGB")


def compute_eraser_edges(edges, brush_width, eraser_width=None):
    """Compute the excess pixels that the eraser should remove.

    eraser_width: the actual in-game eraser width. If None, uses brush_width.
    """
    if eraser_width is None:
        eraser_width = brush_width
    if brush_width <= 2:
        return np.zeros_like(edges)

    pen_kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (brush_width, brush_width))
    thick = cv2.dilate(edges, pen_kern, iterations=1)

    keep_size = min(eraser_width, brush_width - 1)
    if keep_size > 1:
        keep_kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (keep_size, keep_size))
        kept = cv2.dilate(edges, keep_kern, iterations=1)
    else:
        kept = edges

    excess = cv2.subtract(thick, kept)
    return excess


# ---------------------------------------------------------
# Internal edge pipeline (used by optimizer)
# ---------------------------------------------------------

def _get_canny(img, detail, blur, clahe_clip=0.0):
    """Compute bilateral-filtered + CLAHE + adaptive Canny edges."""
    processed = _apply_clahe(img, clahe_clip)
    processed = _apply_bilateral(processed, blur)
    lower, upper = _adaptive_canny_thresholds(processed, detail)
    return cv2.Canny(processed, lower, upper)


def _build_edges(img, detail, blur, edge_close, min_contour_len, canny_cache=None,
                 img_key=None, clahe_clip=0.0):
    """Run the full edge pipeline. Uses canny_cache dict to avoid recomputing blur+canny.

    img_key should be a stable identifier for img (e.g. a string label) rather
    than id(img), since id() can be reused after garbage collection.
    """
    cache_key = (img_key if img_key is not None else id(img), detail, blur, clahe_clip)
    if canny_cache is not None and cache_key in canny_cache:
        edges = canny_cache[cache_key].copy()
    else:
        edges = _get_canny(img, detail, blur, clahe_clip)
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
        coverage = min(1.0, captured / total_gradient)

        edge_pixels = np.count_nonzero(edge_mask)
        if edge_pixels > 0:
            precision = gradient[edge_mask].mean() / max(1.0, gradient.mean())
        else:
            precision = 0

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
    all_pts = []
    contour_ranges = []
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

            for si in range(len(starts_idx)):
                s, e = starts_idx[si], ends_idx[si]
                if s + 1 >= e:
                    continue
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


# ---------------------------------------------------------
# Optimizer
# ---------------------------------------------------------

def optimize_settings(image_path: str, output_dir: str, on_progress=None):
    """Find the fastest settings that produce acceptable drawing quality.

    Phase order matters — each phase depends on the previous:
    1. Edge detection (detail, blur, edge_close, bg_removal, clahe)
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

    # Prepare image variants with stable keys
    variants = [("raw", False, raw_img)]
    cleaned = remove_background(raw_img)
    if not np.array_equal(cleaned, raw_img):
        variants.append(("cleaned", True, cleaned))

    gradients = {}
    for key, _, img in variants:
        gradients[key] = _compute_gradient(img)

    cache = {}

    # --- Phase 1: Coarse edge sweep (25%) ---
    # Now also sweeps CLAHE values
    combos = []
    for key, use_bg, img in variants:
        for detail in range(2, 10, 2):
            for blur in (1, 5, 9, 13, 17):
                for edge_close in (1, 3, 5):
                    for clahe in (0.0, 2.0):
                        combos.append((key, use_bg, img, detail, blur, edge_close, clahe))

    results = []
    total = len(combos)
    for i, (key, use_bg, img, detail, blur, edge_close, clahe) in enumerate(combos):
        if i % 6 == 0:
            _progress(0.20 * (i / total))
        contours = _build_edges(img, detail, blur, edge_close, 0, cache, img_key=key,
                                clahe_clip=clahe)
        if not contours:
            continue
        score = _score_edges(contours, img, gradients[key])
        results.append((score, key, use_bg, img, detail, blur, edge_close, clahe))

    if not results:
        _progress(1.0)
        return {}

    results.sort(key=lambda x: x[0], reverse=True)

    # --- Phase 2: Fine sweep around top 5 (25%) ---
    fine_seen = set()
    fine_combos = []
    for _, ikey, use_bg, img, detail, blur, edge_close, clahe in results[:5]:
        for d in range(max(1, detail - 1), min(11, detail + 2)):
            for b in (max(1, blur - 2), blur, blur + 2):
                for ec in (max(1, edge_close - 2), edge_close, min(9, edge_close + 2)):
                    if ec > 1 and ec % 2 == 0:
                        ec += 1
                    for cl in (max(0.0, clahe - 1.0), clahe, clahe + 1.0):
                        fkey = (ikey, d, b, ec, cl)
                        if fkey not in fine_seen:
                            fine_seen.add(fkey)
                            fine_combos.append((ikey, use_bg, img, d, b, ec, cl))

    fine_results = []
    fine_total = len(fine_combos)
    for i, (ikey, use_bg, img, detail, blur, edge_close, clahe) in enumerate(fine_combos):
        if i % 4 == 0:
            _progress(0.20 + 0.25 * (i / max(1, fine_total)))
        contours = _build_edges(img, detail, blur, edge_close, 0, cache, img_key=ikey,
                                clahe_clip=clahe)
        if not contours:
            continue
        score = _score_edges(contours, img, gradients[ikey])
        fine_results.append((score, ikey, use_bg, img, detail, blur, edge_close, clahe))

    all_results = results + fine_results
    all_results.sort(key=lambda x: x[0], reverse=True)
    _, ikey, use_bg, img, detail, blur, edge_close, clahe = all_results[0]

    _progress(0.50)

    # --- Phase 3: Noise filtering (5%) ---
    contours = _build_edges(img, detail, blur, edge_close, 0, cache, img_key=ikey,
                            clahe_clip=clahe)
    grad = gradients[ikey]

    lengths = [len(c) for c in contours]
    short_ratio = sum(1 for l in lengths if l < 5) / max(1, len(lengths))

    best_min_len = 0
    if short_ratio > 0.3:
        base_score = _score_edges(contours, img, grad)
        for min_len in (4, 6):
            filtered = _build_edges(img, detail, blur, edge_close, min_len, cache,
                                    img_key=ikey, clahe_clip=clahe)
            if filtered:
                s = _score_edges(filtered, img, grad)
                if s > base_score:
                    base_score = s
                    best_min_len = min_len

    contours = _build_edges(img, detail, blur, edge_close, best_min_len, cache,
                            img_key=ikey, clahe_clip=clahe)

    _progress(0.6)

    # --- Phase 4: Thickness (15%) ---
    cache_key = (ikey, detail, blur, clahe)
    if cache_key in cache:
        canny = cache[cache_key].copy()
    else:
        canny = _get_canny(img, detail, blur, clahe)
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
        'clahe_clip': clahe,
    }


# ---------------------------------------------------------
# Font / text utilities
# ---------------------------------------------------------

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
