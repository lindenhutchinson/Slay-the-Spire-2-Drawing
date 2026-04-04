import threading
import keyboard

from spire_painter.mouse import left_click_up, right_click_up


class DrawingState:
    """Thread-safe state machine for drawing pause/resume/abort."""

    def __init__(self):
        self._lock = threading.Lock()
        self._abort = False
        self._pause = False
        self._drawing = False

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

    def trigger_pause(self):
        with self._lock:
            if self._abort or self._pause:
                return
            self._pause = True
            if self._drawing:
                left_click_up()
                right_click_up()
        print("\n[Paused] Triggered! You can safely perform other operations.")

    def trigger_resume(self):
        with self._lock:
            if self._pause:
                self._pause = False
        print("\n[Resumed] Triggered! Drawing resumed.")

    def trigger_abort(self):
        with self._lock:
            self._abort = True
            self._pause = False
            if self._drawing:
                left_click_up()
                right_click_up()
        print("\n[Terminated] Task list destroyed, memory freed!")

    def reset(self):
        with self._lock:
            self._abort = False
            self._pause = False


# Module-level singleton
state = DrawingState()


def setup_hotkeys():
    """Register global keyboard hotkeys for pause/resume/abort."""

    def handle_p_key(e):
        if keyboard.is_pressed('ctrl') or keyboard.is_pressed('alt'):
            return
        state.trigger_pause()

    keyboard.on_press_key('p', handle_p_key)
    keyboard.on_press_key('P', handle_p_key)
    keyboard.add_hotkey('ctrl+alt+p', state.trigger_resume)
    keyboard.on_press_key('[', lambda _: state.trigger_abort())


# Register hotkeys on import
setup_hotkeys()
