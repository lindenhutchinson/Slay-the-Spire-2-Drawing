import atexit
import ctypes
import logging
import time

from spire_painter.constants import MOUSE_ABSOLUTE_MAX

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# DPI Awareness
# ---------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except OSError:
    logger.warning("DPI awareness not available on this system")

# ---------------------------------------------------------
# High-resolution timer (1ms instead of default ~15ms)
# ---------------------------------------------------------
_timer_period_set = False
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
    _timer_period_set = True
except Exception:
    logger.warning("Failed to set high-resolution timer period")


def _cleanup_timer():
    if _timer_period_set:
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass

atexit.register(_cleanup_timer)

# ---------------------------------------------------------
# Windows Mouse Event Constants
# ---------------------------------------------------------
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# ---------------------------------------------------------
# Virtual-screen metrics — refreshed before each drawing session
# ---------------------------------------------------------
_v_left = 0
_v_top = 0
_v_width = 0
_v_height = 0

def refresh_metrics():
    """Re-query virtual screen metrics. Call before each drawing session
    so that resolution changes or monitor (dis)connects are picked up."""
    global _v_left, _v_top, _v_width, _v_height
    _v_left = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    _v_top = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    _v_width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    _v_height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if _v_width == 0 or _v_height == 0:
        _v_width = ctypes.windll.user32.GetSystemMetrics(0)
        _v_height = ctypes.windll.user32.GetSystemMetrics(1)
        _v_left = 0
        _v_top = 0

refresh_metrics()

# ---------------------------------------------------------
# Mouse Control Functions
# ---------------------------------------------------------
_MOVE_FLAGS = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | MOUSEEVENTF_MOVE

def move_mouse(x, y):
    nx = int((x - _v_left) * MOUSE_ABSOLUTE_MAX / _v_width)
    ny = int((y - _v_top) * MOUSE_ABSOLUTE_MAX / _v_height)
    ctypes.windll.user32.mouse_event(_MOVE_FLAGS, nx, ny, 0, 0)

def precise_sleep(seconds):
    """Sleep with ~1ms precision instead of the default ~15ms.
    Uses yielding spin-wait for sub-2ms durations where time.sleep is unreliable."""
    if seconds <= 0:
        return
    if seconds >= 0.002:
        # For longer sleeps, use kernel sleep (now 1ms resolution via timeBeginPeriod)
        time.sleep(seconds)
    else:
        # Yielding spin-wait for very short durations
        target = time.perf_counter() + seconds
        while time.perf_counter() < target:
            time.sleep(0.00001)  # 10µs yield to reduce CPU burn

def right_click_down():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)

def right_click_up():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

def left_click_down():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

def left_click_up():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def middle_click_down():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)

def middle_click_up():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
