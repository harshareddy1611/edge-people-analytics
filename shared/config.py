# config.py — all tunable settings in one place

# Cameras
SCENE_CAMERA_ID = 0      # IMX219 wide — person detection
FACE_CAMERA_ID  = 1      # IMX219 standard — face analytics (Pi Cam 2 on CSI-1)

# Debug / display
# If True, draw boxes/text overlays and show cv2 windows (requires a display).
# Keep False for headless/production runs — saves CPU + RAM.
DEBUG_DRAW      = False

# How often (seconds) to log a face event for the same tracked face when its
# smoothed prediction hasn't changed. Prevents writing a DB row every frame.
FACE_LOG_INTERVAL = 5

# Scene detection
SCENE_WIDTH     = 1280
SCENE_HEIGHT    = 720
SCENE_FPS       = 15
YOLO_WEIGHTS    = "/home/vision/projects/jetson-nano-people-analytics/yolov5n.pt"
YOLO_CONF       = 0.40
YOLO_IOU        = 0.45
YOLO_IMG_SIZE   = 256
MIN_PERSON_W    = 60     # ignore detections smaller than this
MIN_PERSON_H    = 120

# Face analytics
FACE_WIDTH      = 640
FACE_HEIGHT     = 480
FACE_FPS        = 8     # lower FPS — face analytics is heavier

# Tracking
MAX_DISAPPEARED = 50
MAX_DISTANCE    = 100

# Database
DB_PATH         = "/home/vision/projects/people-analytics/data/analytics.db"

# Dashboard
DASHBOARD_HOST  = "0.0.0.0"
DASHBOARD_PORT  = 5000

# Ad selection — demographic windows
# AD_WINDOW_SECS: how often the dominant demographic is re-evaluated and
# the ad category potentially switched. Lower = more responsive, but more
# prone to switching based on momentary misclassifications. 12s gives the
# SMOOTH_BUFFER (10 frames) time to settle while keeping switches snappy.
AD_WINDOW_SECS  = 12     # look at last 12 seconds to decide ad
DWELL_MIN_SECS  = 2      # minimum seconds looking to count as dwell

# Age groups
AGE_GROUPS = ["0-17", "18-28", "29-45", "46+"]

# Ad categories — map (age_group, gender) to ad
AD_CATEGORIES = {
    ("18-28", "Male"):   "gym",
    ("18-28", "Female"): "beauty_salon",
    ("29-45", "Male"):   "finance",
    ("29-45", "Female"): "lifestyle",
    ("0-17",  "Male"):   "gaming",
    ("0-17",  "Female"): "gaming",
    ("46+",   "Male"):   "healthcare",
    ("46+",   "Female"): "healthcare",
}

# ---------------------------------------------------------------------------
# Ad viewer
# ---------------------------------------------------------------------------

# Directory containing one subfolder per ad category, each holding the
# images to slideshow for that category. e.g.:
#   AD_MEDIA_DIR/gym/poster1.jpg
#   AD_MEDIA_DIR/default/welcome.jpg
AD_MEDIA_DIR = "/home/vision/projects/people-analytics/adviewer/ads"

# How long each image is shown before advancing to the next, in seconds.
AD_SLIDE_SECS = 6

# How often the ad viewer polls for the current ad category, in seconds.
# Kept short since this is just a tiny JSON request — low cost, but
# directly adds to the perceived "switch lag" after AD_WINDOW_SECS elapses.
AD_POLL_SECS = 2

AD_VIEWER_HOST = "0.0.0.0"
AD_VIEWER_PORT = 5001
