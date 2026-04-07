import logging
import threading
import time

import keyboard

from spire_painter.mouse import left_click_up, right_click_up, middle_click_up

logger = logging.getLogger(__name__)


class DrawingState:
    """Thread-safe state machine for drawing pause/resume/abort with progress tracking."""

    def __init__(self):
        self._lock = threading.Lock()
        self._abort = False
        self._pause = False
        self._drawing = False
        # Progress tracking
        self._total_points = 0
        self._completed_points = 0
        self._draw_start_time = 0.0

    @property
    def abort(self):
        with self._lock:
            return self._abort

    @abort.setter
    def abort(self, val):
        with self._lock:
            self._abort = val

    @property
    def pause(self):
        with self._lock:
            return self._pause

    @pause.setter
    def pause(self, val):
        with self._lock:
            self._pause = val

    @property
    def drawing(self):
        with self._lock:
            return self._drawing

    @drawing.setter
    def drawing(self, val):
        with self._lock:
            self._drawing = val

    def start_timing(self):
        with self._lock:
            self._draw_start_time = time.time()
            self._completed_points = 0
            self._total_points = 0

    def set_progress(self, completed, total):
        with self._lock:
            self._completed_points = completed
            self._total_points = total

    def get_progress(self):
        """Returns (completed, total, start_time)."""
        with self._lock:
            return self._completed_points, self._total_points, self._draw_start_time

    def trigger_pause(self):
        with self._lock:
            if self._abort or self._pause:
                return
            self._pause = True
            if self._drawing:
                left_click_up()
                right_click_up()
                middle_click_up()
        logger.info("[Paused] Triggered! You can safely perform other operations.")

    def trigger_resume(self):
        with self._lock:
            if self._pause:
                self._pause = False
        logger.info("[Resumed] Triggered! Drawing resumed.")

    def trigger_abort(self):
        with self._lock:
            self._abort = True
            self._pause = False
            if self._drawing:
                left_click_up()
                right_click_up()
                middle_click_up()
        logger.info("[Terminated] Task list destroyed, memory freed!")

    def reset(self):
        with self._lock:
            self._abort = False
            self._pause = False
            self._total_points = 0
            self._completed_points = 0
            self._draw_start_time = 0.0


# Module-level singleton
state = DrawingState()

_hotkeys_registered = False


def setup_hotkeys():
    """Register global keyboard hotkeys for pause/resume/abort.

    Safe to call multiple times — only registers once.
    """
    global _hotkeys_registered
    if _hotkeys_registered:
        return
    _hotkeys_registered = True

    def handle_p_key(e):
        if keyboard.is_pressed('ctrl') or keyboard.is_pressed('alt'):
            return
        state.trigger_pause()

    keyboard.on_press_key('p', handle_p_key)
    keyboard.on_press_key('P', handle_p_key)
    keyboard.add_hotkey('ctrl+alt+p', state.trigger_resume)
    keyboard.on_press_key('[', lambda _: state.trigger_abort())


def cleanup_hotkeys():
    """Unregister all keyboard hooks."""
    global _hotkeys_registered
    if not _hotkeys_registered:
        return
    try:
        keyboard.unhook_all()
    except Exception:
        pass
    _hotkeys_registered = False
