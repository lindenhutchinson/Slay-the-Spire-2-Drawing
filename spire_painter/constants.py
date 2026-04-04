# ---------------------------------------------------------
# Application Constants
# ---------------------------------------------------------

# Window
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
APP_ID = "wzf.spirepainter.v1.1"

# Colors
BG_COLOR = "#F3F3F3"
ACCENT_BLUE = "#2196F3"
ACCENT_GREEN = "#4CAF50"
TEXT_COLOR = "#333333"
TEXT_LIGHT = "#555555"
BORDER_COLOR = "#DDDDDD"
ALERT_RED = "#E53935"

# Font
DEFAULT_FONT = "Microsoft YaHei"

# Font map: display name -> filename
FONT_MAP = {
    "Microsoft YaHei (Default)": "msyh.ttc",
    "SimHei (Bold)": "simhei.ttf",
    "KaiTi (Brush)": "simkai.ttf",
    "SimSun (Sharp)": "simsun.ttc",
    "FangSong (Elegant)": "simfang.ttf",
    "STXingKai (Cursive)": "STXINGKA.TTF",
    "STXinWei (Semi-Cursive)": "STXINWEI.TTF",
    "LiSu (Classical)": "SIMLI.TTF",
    "YouYuan (Rounded)": "SIMYOU.TTF",
    "STCaiYun (Artistic)": "STCAIYUN.TTF",
    "FZShuTi (Graceful)": "FZSTK.TTF",
}

# Config defaults
DEFAULT_DETAIL = 5
DEFAULT_SPEED = 3
DEFAULT_FILL_GAP = 10

# Preview panel
MIN_ZOOM = 0.05
MAX_ZOOM = 10.0
MAX_PREVIEW_DIM = 8000
ZOOM_IN_FACTOR = 1.15
ZOOM_OUT_FACTOR = 0.85
PREVIEW_FIT_SCALE = 0.9

# Crop / selection overlay
MAX_CROP_DISPLAY = (1000, 800)
MIN_SELECTION_SIZE = 10
SCREEN_DIM_FACTOR = 0.5

# Image processing
TEXT_FONT_SIZE = 150
TEXT_PADDING = 20
TEXT_CANNY_LOW = 100
TEXT_CANNY_HIGH = 200
IMAGE_CANNY_LOWER_BASE = 180
IMAGE_CANNY_UPPER_BASE = 250
IMAGE_CANNY_DETAIL_FACTOR = 15
BLUR_KERNEL_BASE = 11

# Drawing engine timing (seconds)
INITIAL_DRAW_DELAY = 1.0
OVERLAY_LAUNCH_DELAY = 300  # milliseconds
CONTOUR_MOVE_DELAY = 0.002
CONTOUR_MOVE_DELAY_SLOW = 0.008  # delay for sharp turns
CONTOUR_SHARP_ANGLE = 90  # degrees — angles tighter than this get slowed down
CONTOUR_PEN_DELAY = 0.005
CONTOUR_JUMP_THRESHOLD = 10
DEFAULT_BRUSH_WIDTH = 3       # simulated brush width for preview (pixels)
CONTOUR_MERGE_THRESHOLD = 8  # max pixel gap to merge contours into one stroke
EDGE_CLOSE_KERNEL = 3        # morphological close kernel size to bridge edge gaps
SWEEP_MOVE_DELAY = 0.002
SWEEP_LINE_DELAY = 0.005
SWEEP_PEN_DELAY = 0.01
SWEEP_PHASE_GAP = 0.1
PAUSE_CHECK_INTERVAL = 0.1
RESUME_BUFFER = 0.1
CLICK_SETTLE_DELAY = 0.02
SWEEP_STEP_MULTIPLIER = 5

# Mouse absolute coordinate scale (Windows API)
MOUSE_ABSOLUTE_MAX = 65535

# Tutorial popup
TUTORIAL_POPUP_DELAY = 500  # milliseconds
