import math
import time

import cv2
import numpy as np

from spire_painter.mouse import (
    move_mouse, left_click_down, left_click_up, right_click_down, right_click_up,
)
from spire_painter.constants import (
    INITIAL_DRAW_DELAY, PAUSE_CHECK_INTERVAL, RESUME_BUFFER, CLICK_SETTLE_DELAY,
    SWEEP_PEN_DELAY, SWEEP_MOVE_DELAY, SWEEP_LINE_DELAY, SWEEP_PHASE_GAP,
    SWEEP_STEP_MULTIPLIER, CONTOUR_PEN_DELAY, CONTOUR_MOVE_DELAY,
    CONTOUR_MOVE_DELAY_SLOW, CONTOUR_SHARP_ANGLE,
)


def _check_pause_state(state, cx, cy, is_left_click):
    """Check and handle pause/abort. Returns False if aborted."""
    if state.abort:
        return False
    if state.pause:
        if is_left_click:
            left_click_up()
        else:
            right_click_up()

        while state.pause:
            time.sleep(PAUSE_CHECK_INTERVAL)
            if state.abort:
                return False

        time.sleep(RESUME_BUFFER)
        move_mouse(cx, cy)
        time.sleep(CLICK_SETTLE_DELAY)
        if is_left_click:
            left_click_down()
        else:
            right_click_down()
        time.sleep(CLICK_SETTLE_DELAY)
    return True


def _pen_down(is_left_click):
    if is_left_click:
        left_click_down()
    else:
        right_click_down()


def _pen_up(is_left_click):
    if is_left_click:
        left_click_up()
    else:
        right_click_up()


def _sweep_axis(state, start_fixed, end_fixed, vary_start, vary_end,
                step, fill_gap, is_left_click, horizontal):
    """Sweep fill along one axis (horizontal or vertical)."""
    current_vary = vary_start
    direction = 1

    move_mouse(
        start_fixed if horizontal else current_vary,
        current_vary if horizontal else start_fixed
    )
    time.sleep(SWEEP_PEN_DELAY)
    _pen_down(is_left_click)
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
            if not _check_pause_state(state, cx, cy, is_left_click):
                break
            move_mouse(cx, cy)
            time.sleep(SWEEP_MOVE_DELAY)

        if state.abort:
            break

        fx = end_pos if horizontal else current_vary
        fy = current_vary if horizontal else end_pos
        move_mouse(fx, fy)
        time.sleep(SWEEP_LINE_DELAY)

        current_vary += fill_gap
        if current_vary <= vary_end:
            nx = end_pos if horizontal else current_vary
            ny = current_vary if horizontal else end_pos
            if not _check_pause_state(state, nx, ny, is_left_click):
                break
            move_mouse(nx, ny)
            time.sleep(SWEEP_LINE_DELAY)

        direction *= -1

    _pen_up(is_left_click)


def draw_fill(state, rx, ry, rw, rh, step, fill_gap, is_left_click):
    """Fog of War double-cross sweep fill."""
    state.drawing = True
    try:
        time.sleep(INITIAL_DRAW_DELAY)

        # Horizontal pass
        _sweep_axis(state, rx, rx + rw, ry, ry + rh,
                    step, fill_gap, is_left_click, horizontal=True)
        time.sleep(SWEEP_PHASE_GAP)

        if state.abort:
            print("Fill was force-terminated, memory reclaimed!")
            return

        # Vertical pass
        _sweep_axis(state, ry, ry + rh, rx, rx + rw,
                    step, fill_gap, is_left_click, horizontal=False)

        if not state.abort:
            print("Fog double-fill complete! Memory auto-reclaimed.")
    finally:
        state.drawing = False


def _angle_between(dx1, dy1, dx2, dy2):
    """Return the angle in degrees between two direction vectors."""
    dot = dx1 * dx2 + dy1 * dy2
    mag1 = math.hypot(dx1, dy1)
    mag2 = math.hypot(dx2, dy2)
    if mag1 == 0 or mag2 == 0:
        return 0.0
    cos_val = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_val))


def _to_screen(point, offset_x, offset_y, scale):
    return int(offset_x + point[0][0] * scale), int(offset_y + point[0][1] * scale)


def draw_contours(state, rx, ry, rw, rh, img_path, step, is_left_click):
    """Draw line art contours with adaptive pen control.

    Straight segments keep the pen down and move fast.
    Sharp turns lift the pen, reposition, then press again to avoid smudging.
    Moderate turns slow down but keep the pen down.
    """
    state.drawing = True
    try:
        time.sleep(INITIAL_DRAW_DELAY)

        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        edges = cv2.bitwise_not(img)

        img_h, img_w = edges.shape
        scale = min(rw / img_w, rh / img_h)

        offset_x = rx + (rw - img_w * scale) / 2
        offset_y = ry + (rh - img_h * scale) / 2

        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

        for contour in contours:
            if state.abort:
                break
            if len(contour) == 0:
                continue

            points = contour[::step]
            if len(points) == 0:
                continue

            # Convert all points to screen coords upfront
            screen_pts = [_to_screen(p, offset_x, offset_y, scale) for p in points]

            # Check pause/abort between contours (safe — pen is up)
            if not _check_pause_state(state, screen_pts[0][0], screen_pts[0][1], is_left_click):
                break

            # Start the first stroke
            pen_is_down = False
            move_mouse(screen_pts[0][0], screen_pts[0][1])
            time.sleep(CONTOUR_PEN_DELAY)
            _pen_down(is_left_click)
            pen_is_down = True
            time.sleep(CONTOUR_PEN_DELAY)

            prev_dx, prev_dy = 0.0, 0.0

            for i in range(1, len(screen_pts)):
                if state.abort:
                    break

                px, py = screen_pts[i]
                prev_px, prev_py = screen_pts[i - 1]
                dx = float(px - prev_px)
                dy = float(py - prev_py)

                # Skip zero-length moves
                if dx == 0.0 and dy == 0.0:
                    continue

                # Calculate turn angle from previous direction
                angle = 0.0
                if prev_dx != 0.0 or prev_dy != 0.0:
                    angle = _angle_between(prev_dx, prev_dy, dx, dy)

                if angle > CONTOUR_SHARP_ANGLE:
                    # Sharp turn: lift pen, move to new position, press again
                    if pen_is_down:
                        _pen_up(is_left_click)
                        pen_is_down = False
                        time.sleep(CONTOUR_PEN_DELAY)

                    move_mouse(px, py)
                    time.sleep(CONTOUR_PEN_DELAY)

                    _pen_down(is_left_click)
                    pen_is_down = True
                    time.sleep(CONTOUR_PEN_DELAY)

                elif angle > CONTOUR_SHARP_ANGLE * 0.5:
                    # Moderate turn: keep pen down, slow down
                    if not pen_is_down:
                        _pen_down(is_left_click)
                        pen_is_down = True
                        time.sleep(CONTOUR_PEN_DELAY)

                    move_mouse(px, py)
                    t = (angle - CONTOUR_SHARP_ANGLE * 0.5) / (CONTOUR_SHARP_ANGLE * 0.5)
                    delay = CONTOUR_MOVE_DELAY + t * (CONTOUR_MOVE_DELAY_SLOW - CONTOUR_MOVE_DELAY)
                    time.sleep(delay)

                else:
                    # Straight: keep pen down, full speed
                    if not pen_is_down:
                        _pen_down(is_left_click)
                        pen_is_down = True
                        time.sleep(CONTOUR_PEN_DELAY)

                    move_mouse(px, py)
                    time.sleep(CONTOUR_MOVE_DELAY)

                prev_dx, prev_dy = dx, dy

                # Lightweight abort check (no pen manipulation)
                if state.pause:
                    if pen_is_down:
                        _pen_up(is_left_click)
                        pen_is_down = False
                    while state.pause:
                        time.sleep(PAUSE_CHECK_INTERVAL)
                        if state.abort:
                            break

            # End of contour — ensure pen is up
            if pen_is_down:
                _pen_up(is_left_click)
                pen_is_down = False
                time.sleep(CONTOUR_PEN_DELAY)

        if state.abort:
            print("Drawing task was force-terminated!")
        else:
            print("Drawing completed successfully! Memory auto-freed.")
    finally:
        state.drawing = False
