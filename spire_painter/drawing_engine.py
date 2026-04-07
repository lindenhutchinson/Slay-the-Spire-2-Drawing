import logging
import math
import time

import cv2
import numpy as np

from spire_painter.mouse import (
    move_mouse, precise_sleep, refresh_metrics,
    left_click_down, left_click_up,
    right_click_down, right_click_up,
    middle_click_down, middle_click_up,
)
from spire_painter.constants import (
    INITIAL_DRAW_DELAY, PAUSE_CHECK_INTERVAL, RESUME_BUFFER, CLICK_SETTLE_DELAY,
    SWEEP_PEN_DELAY, SWEEP_MOVE_DELAY, SWEEP_LINE_DELAY, SWEEP_PHASE_GAP,
    SWEEP_STEP_MULTIPLIER, CONTOUR_PEN_DELAY, CONTOUR_MOVE_DELAY,
    CONTOUR_MOVE_DELAY_SLOW, CONTOUR_SHARP_ANGLE, CONTOUR_MERGE_THRESHOLD,
    EDGE_CLOSE_KERNEL, DEFAULT_BRUSH_WIDTH, DEFAULT_ERASER_WIDTH,
    TWO_OPT_MAX_ITERATIONS, TWO_OPT_MAX_STROKES, BEZIER_MAX_ERROR,
)
from spire_painter.image_processing import (
    compute_eraser_edges, fit_bezier_contour, generate_hatching,
)

logger = logging.getLogger(__name__)

# Draw modes: "right" = draw (StS2), "left" = draw (Paint), "middle" = eraser
DRAW_MODE_LEFT = "left"
DRAW_MODE_RIGHT = "right"
DRAW_MODE_MIDDLE = "middle"

# Precompute turn thresholds as cosine values (avoids acos/degrees per point)
_COS_SHARP = math.cos(math.radians(CONTOUR_SHARP_ANGLE))
_COS_MODERATE = math.cos(math.radians(CONTOUR_SHARP_ANGLE * 0.5))


def _pen_down(draw_mode):
    if draw_mode == DRAW_MODE_LEFT:
        left_click_down()
    elif draw_mode == DRAW_MODE_MIDDLE:
        middle_click_down()
    else:
        right_click_down()


def _pen_up(draw_mode):
    if draw_mode == DRAW_MODE_LEFT:
        left_click_up()
    elif draw_mode == DRAW_MODE_MIDDLE:
        middle_click_up()
    else:
        right_click_up()


def _pen_up_all():
    """Safety: release all mouse buttons."""
    left_click_up()
    right_click_up()
    middle_click_up()


def _check_pause_state(state, cx, cy, draw_mode):
    """Check and handle pause/abort. Returns False if aborted."""
    if state.abort:
        return False
    if state.pause:
        _pen_up(draw_mode)

        while state.pause:
            time.sleep(PAUSE_CHECK_INTERVAL)
            if state.abort:
                return False

        time.sleep(RESUME_BUFFER)
        move_mouse(cx, cy)
        time.sleep(CLICK_SETTLE_DELAY)
        _pen_down(draw_mode)
        time.sleep(CLICK_SETTLE_DELAY)
    return True


# ---------------------------------------------------------
# Sweep fill (Fog of War)
# ---------------------------------------------------------

def _sweep_axis(state, start_fixed, end_fixed, vary_start, vary_end,
                step, fill_gap, draw_mode, horizontal):
    """Sweep fill along one axis (horizontal or vertical)."""
    current_vary = vary_start
    direction = 1

    move_mouse(
        start_fixed if horizontal else current_vary,
        current_vary if horizontal else start_fixed
    )
    time.sleep(SWEEP_PEN_DELAY)
    _pen_down(draw_mode)
    time.sleep(SWEEP_PEN_DELAY)

    while current_vary <= vary_end:
        if state.abort:
            break

        start_pos = start_fixed if direction == 1 else end_fixed
        end_pos = end_fixed if direction == 1 else start_fixed

        dist = abs(end_pos - start_pos)
        jump_pixels = step * SWEEP_STEP_MULTIPLIER
        steps = int(max(1, dist // jump_pixels))

        for i in range(1, steps + 1):
            cur = start_pos + (end_pos - start_pos) * i / steps
            cx = cur if horizontal else current_vary
            cy = current_vary if horizontal else cur
            if not _check_pause_state(state, cx, cy, draw_mode):
                break
            move_mouse(cx, cy)
            precise_sleep(SWEEP_MOVE_DELAY)

        if state.abort:
            break

        fx = end_pos if horizontal else current_vary
        fy = current_vary if horizontal else end_pos
        move_mouse(fx, fy)
        precise_sleep(SWEEP_LINE_DELAY)

        current_vary += fill_gap
        if current_vary <= vary_end:
            nx = end_pos if horizontal else current_vary
            ny = current_vary if horizontal else end_pos
            if not _check_pause_state(state, nx, ny, draw_mode):
                break
            move_mouse(nx, ny)
            precise_sleep(SWEEP_LINE_DELAY)

        direction *= -1

    _pen_up(draw_mode)


def draw_fill(state, rx, ry, rw, rh, step, fill_gap, draw_mode):
    """Fog of War double-cross sweep fill."""
    state.drawing = True
    try:
        time.sleep(INITIAL_DRAW_DELAY)

        _sweep_axis(state, rx, rx + rw, ry, ry + rh,
                    step, fill_gap, draw_mode, horizontal=True)
        time.sleep(SWEEP_PHASE_GAP)

        if state.abort:
            logger.info("Fill was force-terminated!")
            return

        _sweep_axis(state, ry, ry + rh, rx, rx + rw,
                    step, fill_gap, draw_mode, horizontal=False)

        if not state.abort:
            logger.info("Fog double-fill complete!")
    finally:
        _pen_up_all()
        state.drawing = False


# ---------------------------------------------------------
# Contour drawing helpers
# ---------------------------------------------------------

def _cos_between(dx1, dy1, dx2, dy2):
    """Return the cosine of the angle between two direction vectors.
    Returns 1.0 (straight) to -1.0 (reversal). Avoids trig calls."""
    dot = dx1 * dx2 + dy1 * dy2
    mag_sq = (dx1 * dx1 + dy1 * dy1) * (dx2 * dx2 + dy2 * dy2)
    if mag_sq == 0:
        return 1.0
    return dot / math.sqrt(mag_sq)


def _to_screen(point, offset_x, offset_y, scale):
    return int(offset_x + point[0][0] * scale), int(offset_y + point[0][1] * scale)


def _dedup_points(points):
    """Remove consecutive duplicate screen coordinates.
    When scale < 1, many contour pixels map to the same screen pixel."""
    if not points:
        return points
    deduped = [points[0]]
    for p in points[1:]:
        if p != deduped[-1]:
            deduped.append(p)
    return deduped


def _dist_sq(p1, p2):
    """Squared Euclidean distance between two (x, y) tuples."""
    return (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2


# ---------------------------------------------------------
# 2-opt stroke ordering improvement
# ---------------------------------------------------------

def _two_opt_improve(ordered, strokes):
    """Improve stroke ordering using 2-opt TSP heuristic.

    ordered: list of (stroke_idx, reversed_flag)
    strokes: original stroke point lists
    Returns improved ordered list.
    """
    if len(ordered) < 4:
        return ordered

    def _endpoint(idx, rev):
        pts = strokes[idx]
        return pts[-1] if not rev else pts[0]

    def _startpoint(idx, rev):
        pts = strokes[idx]
        return pts[0] if not rev else pts[-1]

    def _segment_cost(i, j):
        """Travel cost between end of ordered[i] and start of ordered[j]."""
        ep = _endpoint(*ordered[i])
        sp = _startpoint(*ordered[j])
        return math.sqrt(_dist_sq(ep, sp))

    n = len(ordered)
    improved = True
    iterations = 0

    while improved and iterations < TWO_OPT_MAX_ITERATIONS:
        improved = False
        iterations += 1
        for i in range(n - 2):
            for j in range(i + 2, n):
                if j == n - 1 and i == 0:
                    continue  # skip full reversal

                # Current cost: edge (i, i+1) + edge (j, j+1 if exists)
                old_cost = _segment_cost(i, i + 1)
                if j + 1 < n:
                    old_cost += _segment_cost(j, j + 1)

                # Reverse the segment [i+1..j]
                # New edges: (i, j) + (i+1, j+1 if exists)
                # After reversal, ordered[i+1] becomes ordered[j] (reversed)
                # and ordered[j] becomes ordered[i+1] (reversed)
                trial = ordered[:i + 1] + [(idx, not rev) for idx, rev in reversed(ordered[i + 1:j + 1])]
                if j + 1 < n:
                    trial += ordered[j + 1:]

                new_cost = 0
                ep_i = _endpoint(*trial[i])
                sp_ip1 = _startpoint(*trial[i + 1])
                new_cost += math.sqrt(_dist_sq(ep_i, sp_ip1))
                if j + 1 < n:
                    ep_j = _endpoint(*trial[j])
                    sp_jp1 = _startpoint(*trial[j + 1])
                    new_cost += math.sqrt(_dist_sq(ep_j, sp_jp1))

                if new_cost < old_cost - 0.5:  # small threshold to avoid floating point churn
                    ordered = trial
                    improved = True

    return ordered


def _order_and_merge_strokes(strokes, merge_threshold, use_two_opt=True):
    """Reorder strokes by nearest-neighbor and merge close endpoints into
    continuous drawing sequences.

    Each stroke is a list of (x, y) screen-coordinate tuples.
    Returns a list of *merged* strokes — sequences of points that can be drawn
    without lifting the pen.
    """
    if not strokes:
        return []

    merge_sq = merge_threshold ** 2
    remaining = list(range(len(strokes)))
    ordered = []

    # Filter out empty strokes
    remaining = [i for i in remaining if len(strokes[i]) >= 2]
    if not remaining:
        return []

    # Start with the stroke closest to origin (top-left first)
    best_idx = 0
    best_dist = _dist_sq(strokes[remaining[0]][0], (0, 0))
    for i, idx in enumerate(remaining):
        d = _dist_sq(strokes[idx][0], (0, 0))
        if d < best_dist:
            best_dist = d
            best_idx = i
    first = remaining.pop(best_idx)
    ordered.append((first, False))  # (stroke_index, reversed)

    # Greedy nearest-neighbor ordering with direction optimization
    while remaining:
        last_stroke_idx, last_reversed = ordered[-1]
        last_pts = strokes[last_stroke_idx]
        cursor = last_pts[0] if last_reversed else last_pts[-1]

        best_i = 0
        best_reversed = False
        best_dist = float('inf')

        for i, idx in enumerate(remaining):
            pts = strokes[idx]
            d_start = _dist_sq(cursor, pts[0])
            d_end = _dist_sq(cursor, pts[-1])

            if d_start <= d_end:
                if d_start < best_dist:
                    best_dist = d_start
                    best_i = i
                    best_reversed = False
            else:
                if d_end < best_dist:
                    best_dist = d_end
                    best_i = i
                    best_reversed = True

        chosen = remaining.pop(best_i)
        ordered.append((chosen, best_reversed))

    # 2-opt improvement (skip for very large stroke sets)
    if use_two_opt and len(ordered) <= TWO_OPT_MAX_STROKES:
        ordered = _two_opt_improve(ordered, strokes)

    # Build merged strokes — connect strokes that end close to the next start.
    merged = []
    current_merged = []

    for stroke_idx, reversed_flag in ordered:
        pts = strokes[stroke_idx]
        if reversed_flag:
            pts = list(reversed(pts))

        if not current_merged:
            current_merged = list(pts)
        else:
            gap = _dist_sq(current_merged[-1], pts[0])
            if gap <= merge_sq:
                current_merged.append(None)
                current_merged.extend(pts)
            else:
                merged.append(current_merged)
                current_merged = list(pts)

    if current_merged:
        merged.append(current_merged)

    return merged


# ---------------------------------------------------------
# Stroke drawing
# ---------------------------------------------------------

def _split_at_sentinels(pts):
    """Split a merged stroke list at None sentinels into sub-strokes."""
    sub = []
    current = []
    for p in pts:
        if p is None:
            if current:
                sub.append(current)
                current = []
        else:
            current.append(p)
    if current:
        sub.append(current)
    return sub


def _draw_stroke(state, screen_pts, draw_mode):
    """Draw a single merged stroke with adaptive pen control.
    Splits at None sentinels to ensure pen lifts between sub-strokes.
    Returns False if aborted."""
    if not screen_pts:
        return True

    sub_strokes = _split_at_sentinels(screen_pts)

    for sub in sub_strokes:
        if state.abort:
            return False
        if not sub:
            continue
        if not _draw_sub_stroke(state, sub, draw_mode):
            return False

    return True


def _draw_sub_stroke(state, screen_pts, draw_mode):
    """Draw a single continuous sub-stroke. Returns False if aborted."""
    if not screen_pts:
        return True

    start_x, start_y = screen_pts[0]

    if not _check_pause_state(state, start_x, start_y, draw_mode):
        return False

    move_mouse(start_x, start_y)
    precise_sleep(CONTOUR_PEN_DELAY)
    _pen_down(draw_mode)
    pen_is_down = True
    precise_sleep(CONTOUR_PEN_DELAY)

    prev_dx, prev_dy = 0.0, 0.0

    for i in range(1, len(screen_pts)):
        if state.abort:
            break

        px, py = screen_pts[i]
        prev_px, prev_py = screen_pts[i - 1]
        dx = float(px - prev_px)
        dy = float(py - prev_py)

        if dx == 0.0 and dy == 0.0:
            continue

        cos_val = 1.0
        if prev_dx != 0.0 or prev_dy != 0.0:
            cos_val = _cos_between(prev_dx, prev_dy, dx, dy)

        if cos_val < _COS_SHARP:
            if pen_is_down:
                _pen_up(draw_mode)
                pen_is_down = False
                precise_sleep(CONTOUR_PEN_DELAY)

            move_mouse(px, py)
            precise_sleep(CONTOUR_PEN_DELAY)

            _pen_down(draw_mode)
            pen_is_down = True
            precise_sleep(CONTOUR_PEN_DELAY)

        elif cos_val < _COS_MODERATE:
            if not pen_is_down:
                _pen_down(draw_mode)
                pen_is_down = True
                precise_sleep(CONTOUR_PEN_DELAY)

            move_mouse(px, py)
            t = (_COS_MODERATE - cos_val) / (_COS_MODERATE - _COS_SHARP)
            delay = CONTOUR_MOVE_DELAY + t * (CONTOUR_MOVE_DELAY_SLOW - CONTOUR_MOVE_DELAY)
            precise_sleep(delay)

        else:
            if not pen_is_down:
                _pen_down(draw_mode)
                pen_is_down = True
                precise_sleep(CONTOUR_PEN_DELAY)

            move_mouse(px, py)
            precise_sleep(CONTOUR_MOVE_DELAY)

        prev_dx, prev_dy = dx, dy

        if state.pause:
            if pen_is_down:
                _pen_up(draw_mode)
                pen_is_down = False

            while state.pause:
                time.sleep(PAUSE_CHECK_INTERVAL)
                if state.abort:
                    break

            if not state.abort:
                time.sleep(RESUME_BUFFER)
                move_mouse(px, py)
                _pen_down(draw_mode)
                pen_is_down = True
                precise_sleep(CLICK_SETTLE_DELAY)

    if pen_is_down:
        _pen_up(draw_mode)
        precise_sleep(CONTOUR_PEN_DELAY)

    return not state.abort


# ---------------------------------------------------------
# Main contour drawing entry point
# ---------------------------------------------------------

def _contours_to_strokes(contours, step, offset_x, offset_y, scale, merge_threshold,
                         bezier_fitting=False):
    """Convert OpenCV contours to ordered, merged screen-coordinate strokes."""
    strokes = []
    for contour in contours:
        if len(contour) == 0:
            continue
        points = contour[::step]
        if len(points) == 0:
            continue
        screen_pts = [_to_screen(p, offset_x, offset_y, scale) for p in points]
        screen_pts = _dedup_points(screen_pts)
        if len(screen_pts) < 2:
            continue

        if bezier_fitting and len(screen_pts) >= 3:
            screen_pts = fit_bezier_contour(screen_pts)
            if len(screen_pts) < 2:
                continue

        strokes.append(screen_pts)

    return _order_and_merge_strokes(strokes, merge_threshold)


def _draw_strokes(state, strokes, draw_mode, progress_offset=0):
    """Draw a list of merged strokes. Returns False if aborted.

    progress_offset: number of points already completed (for progress tracking).
    """
    accumulated = progress_offset
    for stroke in strokes:
        if state.abort:
            return False
        _pen_up(draw_mode)
        if not _draw_stroke(state, stroke, draw_mode):
            return False
        # Count non-None points in this stroke
        pts_in_stroke = sum(1 for p in stroke if p is not None)
        accumulated += pts_in_stroke
        state.set_progress(accumulated, state.get_progress()[1])
    return True


def _has_fine_detail(contour, coarse_step):
    """Check if a contour has significant detail that would be lost at coarse_step.

    Returns True if the contour is short or has high curvature segments.
    """
    n = len(contour)
    # Short contours are always "fine detail"
    if n < coarse_step * 3:
        return True

    # Check curvature: sample at coarse_step and measure deviation
    pts = contour[:, 0, :].astype(np.float32)
    max_dev = 0.0

    for i in range(0, n - coarse_step, coarse_step):
        end = min(i + coarse_step, n - 1)
        if end <= i + 1:
            continue
        p1 = pts[i]
        p2 = pts[end]
        d = p2 - p1
        seg_len = np.sqrt(d[0]**2 + d[1]**2)
        if seg_len < 0.5:
            continue

        intermediates = pts[i + 1:end] - p1
        cross = np.abs(d[0] * intermediates[:, 1] - d[1] * intermediates[:, 0])
        dev = cross.max() / seg_len
        if dev > max_dev:
            max_dev = dev

    return max_dev > 3.0  # high curvature threshold


def draw_contours(state, rx, ry, rw, rh, img_path, step, draw_mode,
                  edge_close=EDGE_CLOSE_KERNEL, eraser_refine=False,
                  brush_width=DEFAULT_BRUSH_WIDTH, eraser_width=DEFAULT_ERASER_WIDTH,
                  bezier_fitting=False, hatching_enabled=False, hatching_density=4,
                  multi_resolution=False, source_gray_path=None):
    """Draw line art contours with all feature options.

    When eraser_refine is True, does a three-pass draw:
    1. Draw all contours with pen (thick lines)
    2. Erase the excess with middle click
    3. Redraw the original contours with pen to restore detail

    When multi_resolution is True, does a two-pass draw:
    1. Coarse pass at 2x speed for structure
    2. Fine pass for high-curvature detail only
    """
    state.drawing = True
    state.start_timing()
    try:
        refresh_metrics()
        time.sleep(INITIAL_DRAW_DELAY)

        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None or img.size == 0:
            logger.error("Failed to load image: %s", img_path)
            return

        edges = cv2.bitwise_not(img)
        img_h, img_w = edges.shape
        if img_w == 0 or img_h == 0:
            logger.error("Image has zero dimensions")
            return

        if edge_close > 1:
            close_kern = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (edge_close, edge_close)
            )
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, close_kern)

        scale = min(rw / img_w, rh / img_h)
        offset_x = rx + (rw - img_w * scale) / 2
        offset_y = ry + (rh - img_h * scale) / 2
        merge_threshold = int(CONTOUR_MERGE_THRESHOLD * scale) if scale > 1 else CONTOUR_MERGE_THRESHOLD

        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

        # Load source grayscale for hatching if needed
        hatch_strokes = []
        if hatching_enabled and source_gray_path:
            try:
                source_gray = cv2.imdecode(
                    np.fromfile(source_gray_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE
                )
                if source_gray is not None:
                    # Resize source_gray to match lineart dimensions
                    source_gray = cv2.resize(source_gray, (img_w, img_h))
                    hatch_contours = generate_hatching(source_gray, levels=hatching_density)
                    hatch_strokes = _contours_to_strokes(
                        hatch_contours, max(1, step), offset_x, offset_y, scale, merge_threshold
                    )
            except Exception as e:
                logger.warning("Hatching generation failed: %s", e)

        if multi_resolution:
            # --- Multi-resolution: coarse then fine ---
            coarse_step = step * 2

            # Coarse pass: all contours at double speed
            coarse_strokes = _contours_to_strokes(
                contours, coarse_step, offset_x, offset_y, scale, merge_threshold,
                bezier_fitting=bezier_fitting,
            )

            # Fine pass: only contours with fine detail
            fine_contours = [c for c in contours if _has_fine_detail(c, coarse_step)]
            fine_strokes = _contours_to_strokes(
                fine_contours, step, offset_x, offset_y, scale, merge_threshold,
                bezier_fitting=bezier_fitting,
            )

            total_pts = (
                sum(sum(1 for p in s if p is not None) for s in coarse_strokes) +
                sum(sum(1 for p in s if p is not None) for s in fine_strokes) +
                sum(sum(1 for p in s if p is not None) for s in hatch_strokes)
            )
            state.set_progress(0, total_pts)

            logger.info("Multi-res pass 1 (coarse): %d strokes", len(coarse_strokes))
            if not _draw_strokes(state, coarse_strokes, draw_mode, progress_offset=0):
                logger.info("Drawing task was force-terminated!")
                return

            coarse_pts = sum(sum(1 for p in s if p is not None) for s in coarse_strokes)

            logger.info("Multi-res pass 2 (fine): %d strokes", len(fine_strokes))
            if not _draw_strokes(state, fine_strokes, draw_mode, progress_offset=coarse_pts):
                logger.info("Drawing task was force-terminated!")
                return

            offset_after_fine = coarse_pts + sum(sum(1 for p in s if p is not None) for s in fine_strokes)

        else:
            # --- Standard single-pass ---
            draw_strokes = _contours_to_strokes(
                contours, step, offset_x, offset_y, scale, merge_threshold,
                bezier_fitting=bezier_fitting,
            )

            total_pts = (
                sum(sum(1 for p in s if p is not None) for s in draw_strokes) +
                sum(sum(1 for p in s if p is not None) for s in hatch_strokes)
            )
            state.set_progress(0, total_pts)

            logger.info("Pass 1 (draw): %d strokes", len(draw_strokes))
            if not _draw_strokes(state, draw_strokes, draw_mode, progress_offset=0):
                logger.info("Drawing task was force-terminated!")
                return

            offset_after_fine = sum(sum(1 for p in s if p is not None) for s in draw_strokes)

            # --- Eraser refinement ---
            if eraser_refine and brush_width > 2 and not state.abort:
                eraser_edges = compute_eraser_edges(edges, brush_width, eraser_width)
                eraser_contours, _ = cv2.findContours(
                    eraser_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
                )
                eraser_strokes = _contours_to_strokes(
                    eraser_contours, step, offset_x, offset_y, scale, merge_threshold
                )

                logger.info("Pass 2 (erase): %d strokes", len(eraser_strokes))
                time.sleep(0.2)
                if not _draw_strokes(state, eraser_strokes, DRAW_MODE_MIDDLE):
                    logger.info("Drawing task was force-terminated!")
                    return

                logger.info("Pass 3 (redraw): %d strokes", len(draw_strokes))
                time.sleep(0.2)
                if not _draw_strokes(state, draw_strokes, draw_mode):
                    logger.info("Drawing task was force-terminated!")
                    return

        # --- Hatching pass ---
        if hatch_strokes and not state.abort:
            logger.info("Hatching pass: %d strokes", len(hatch_strokes))
            if not _draw_strokes(state, hatch_strokes, draw_mode, progress_offset=offset_after_fine):
                logger.info("Drawing task was force-terminated!")
                return

        if not state.abort:
            logger.info("Drawing completed successfully!")
        else:
            logger.info("Drawing task was force-terminated!")
    finally:
        _pen_up_all()
        state.drawing = False
