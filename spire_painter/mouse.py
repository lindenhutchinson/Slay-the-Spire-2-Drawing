import ctypes

from spire_painter.constants import MOUSE_ABSOLUTE_MAX

# ---------------------------------------------------------
# DPI Awareness
# ---------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except OSError:
    pass

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

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# ---------------------------------------------------------
# Mouse Control Functions
# ---------------------------------------------------------
def move_mouse(x, y):
    v_left = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    v_top = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    v_width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    v_height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    if v_width == 0 or v_height == 0:
        v_width = ctypes.windll.user32.GetSystemMetrics(0)
        v_height = ctypes.windll.user32.GetSystemMetrics(1)
        v_left = 0
        v_top = 0

    nx = int((x - v_left) * MOUSE_ABSOLUTE_MAX / v_width)
    ny = int((y - v_top) * MOUSE_ABSOLUTE_MAX / v_height)
    ctypes.windll.user32.mouse_event(
        MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | MOUSEEVENTF_MOVE,
        nx, ny, 0, 0
    )

def right_click_down():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)

def right_click_up():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

def left_click_down():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

def left_click_up():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
