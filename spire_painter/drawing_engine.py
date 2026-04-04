import math
import time

import cv2
import numpy as np

from spire_painter.mouse import (
    move_mouse, precise_sleep,
    left_click_down, left_click_up,
    right_click_down, right_click_up,
    middle_click_down, middle_click_up,
)
from spire_painter.constants import (
    INITIAL_DRAW_DELAY, PAUSE_CHECK_INTERVAL, RESUME_BUFFER, CLICK_SETTLE_DELAY,
    SWEEP_PEN_DELAY, SWEEP_MOVE_DELAY, SWEEP_LINE_DELAY, SWEEP_PHASE_GAP,
    SWEEP_STEP_MULTIPLIER, CONTOUR_PEN_DELAY, CONTOUR_MOVE_DELAY,
    CONTOUR_MOVE_DELAY_SLOW, CONTOUR_SHARP_ANGLE, CONTOUR_MERGE_THRESHOLD,
    EDGE_CLOSE_KERNEL, DEFAULT_BRUSH_WIDTH,
)
from spire_painter.image_processing import compute_eraser_edges

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
            print("Fill was force-terminated!")
            return

        _sweep_axis(state, ry, ry + rh, rx, rx + rw,
                    step, fill_gap, draw_mode, horizontal=False)

        if not state.abort:
            print("Fog double-fill complete!")
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


def _order_and_merge_strokes(strokes, merge_threshold):
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

    # Build merged strokes — connect strokes that end close to the next start.
    # Insert a None sentinel between merged sub-strokes so _draw_stroke knows
    # to lift the pen, move, and put pen back down at the join point.
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
                # Mark the boundary so the pen lifts across the gap
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

def _draw_stroke(state, screen_pts, draw_mode):
    """Draw a single merged stroke with adaptive pen control.
    Returns False if aborted."""
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

        # None sentinel = merge boundary, lift pen and jump
        if screen_pts[i] is None or screen_pts[i - 1] is None:
            if screen_pts[i] is None:
                # Current is sentinel, lift pen
                if pen_is_down:
                    _pen_up(draw_mode)
                    pen_is_down = False
                    precise_sleep(CONTOUR_PEN_DELAY)
                prev_dx, prev_dy = 0.0, 0.0
            continue

        px, py = screen_pts[i]
        prev_idx = i - 1
        while prev_idx >= 0 and screen_pts[prev_idx] is None:
            prev_idx -= 1
        if prev_idx < 0:
            prev_px, prev_py = px, py
        else:
            prev_px, prev_py = screen_pts[prev_idx]

        dx = float(px - prev_px)
        dy = float(py - prev_py)

        if dx == 0.0 and dy == 0.0:
            continue

        cos_val = 1.0
        if prev_dx != 0.0 or prev_dy != 0.0:
            cos_val = _cos_between(prev_dx, prev_dy, dx, dy)

        if cos_val < _COS_SHARP:
            # Sharp turn: lift pen, move, press again
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
            # Moderate turn: slow down
            if not pen_is_down:
                _pen_down(draw_mode)
                pen_is_down = True
                precise_sleep(CONTOUR_PEN_DELAY)

            move_mouse(px, py)
            t = (_COS_MODERATE - cos_val) / (_COS_MODERATE - _COS_SHARP)
            delay = CONTOUR_MOVE_DELAY + t * (CONTOUR_MOVE_DELAY_SLOW - CONTOUR_MOVE_DELAY)
            precise_sleep(delay)

        else:
            # Straight move
            if not pen_is_down:
                _pen_down(draw_mode)
                pen_is_down = True
                precise_sleep(CONTOUR_PEN_DELAY)

            move_mouse(px, py)
            precise_sleep(CONTOUR_MOVE_DELAY)

        prev_dx, prev_dy = dx, dy

        # Handle pause mid-stroke
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

def _contours_to_strokes(contours, step, offset_x, offset_y, scale, merge_threshold):
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
        strokes.append(screen_pts)

    return _order_and_merge_strokes(strokes, merge_threshold)


def _draw_strokes(state, strokes, draw_mode):
    """Draw a list of merged strokes. Returns False if aborted."""
    for stroke in strokes:
        if state.abort:
            return False
        _pen_up(draw_mode)
        if not _draw_stroke(state, stroke, draw_mode):
            return False
    return True


def draw_contours(state, rx, ry, rw, rh, img_path, step, draw_mode,
                  edge_close=EDGE_CLOSE_KERNEL, eraser_refine=False,
                  brush_width=DEFAULT_BRUSH_WIDTH):
    """Draw line art contours. When eraser_refine is True, does a three-pass draw:
    1. Draw all contours with pen (thick lines)
    2. Erase the excess with middle click (eraser is wider than pen, so overshoots)
    3. Redraw the original contours with pen to restore detail the eraser ate
    """
    state.drawing = True
    try:
        time.sleep(INITIAL_DRAW_DELAY)

        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"Failed to load image: {img_path}")
            return

        edges = cv2.bitwise_not(img)
        img_h, img_w = edges.shape
        if img_w == 0 or img_h == 0:
            print("Image has zero dimensions")
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

        # Build strokes from original edges
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        draw_strokes = _contours_to_strokes(contours, step, offset_x, offset_y, scale, merge_threshold)

        # --- Pass 1: Draw with pen ---
        print(f"Pass 1 (draw): {len(draw_strokes)} strokes")
        if not _draw_strokes(state, draw_strokes, draw_mode):
            print("Drawing task was force-terminated!")
            return

        # --- Pass 2 & 3: Eraser refinement ---
        if eraser_refine and brush_width > 2 and not state.abort:
            eraser_edges = compute_eraser_edges(edges, brush_width)
            eraser_contours, _ = cv2.findContours(eraser_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
            eraser_strokes = _contours_to_strokes(eraser_contours, step, offset_x, offset_y, scale, merge_threshold)

            # Pass 2: Erase the excess
            print(f"Pass 2 (erase): {len(eraser_strokes)} strokes")
            time.sleep(0.2)
            if not _draw_strokes(state, eraser_strokes, DRAW_MODE_MIDDLE):
                print("Drawing task was force-terminated!")
                return

            # Pass 3: Redraw original edges to restore detail eraser ate
            print(f"Pass 3 (redraw): {len(draw_strokes)} strokes")
            time.sleep(0.2)
            if not _draw_strokes(state, draw_strokes, draw_mode):
                print("Drawing task was force-terminated!")
                return

        if not state.abort:
            print("Drawing completed successfully!")
        else:
            print("Drawing task was force-terminated!")
    finally:
        _pen_up_all()
        state.drawing = False
