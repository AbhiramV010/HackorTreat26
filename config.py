"""Every constant from the spec's Constants table, plus a few paths."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
SCENES_PATH = os.path.join(DATA_DIR, "scenes.json")
LAST_THEME_PATH = os.path.join(DATA_DIR, "last_theme.txt")

COMPANION_NAME = "Rigor"
SERIAL_BAUD = 115200
PAN_CENTER_DEG = 90
SWEEP_FROM_DEG, SWEEP_TO_DEG = 20, 160
SWEEP_STEP_DEG = 10
SWEEP_PASSES = 1
PAN_SETTLE_MS = 150
STEPS_PER_REV = 2048
PAN_RPM = 10
PINGS_PER_ANGLE, PING_GAP_MS = 3, 30
ECHO_TIMEOUT_US = 25000
MIN_VALID_CM, MAX_VALID_CM = 20, 300
CONTACT_MARGIN_CM = 25
MERGE_GAP_STEPS = 1
MERGE_MAX_DIST_DIFF_CM = 60
PERSON_WIDTH_CM = 45
CLOSE_CM = 100
LEFT_MAX_DEG, RIGHT_MIN_DEG = 70, 110
MIRROR_ANGLES = False
THREAT_FEW_MAX = 2
MORSE_FREQ_HZ = 650
MORSE_UNIT_S = 0.12
MESSAGE_MAX_LETTERS, MESSAGE_MAX_WORDS = 10, 2
SPIDER_LINE_MAX_WORDS = 20
SCENE_MAX_WORDS, REACTION_MAX_WORDS = 30, 20
JOB1_CAP_S = 5.0
JOB2_CAP_S = 6.0
WAKE_MIN_S = 3.0
DECODE_REVEAL_DELAY_S = 1.0

# Pan limits (joystick and l/r/c keys live in the firmware; the HUD has no pan keys)
PAN_MIN_DEG, PAN_MAX_DEG = 20, 160

# Ollama
OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "gemma3:4b"
FALLBACK_MODEL = "gemma3:1b"

# Speech
SPIDER_VOICE = os.path.join(ROOT, "voices", "en_US-lessac-medium.onnx")  # Piper model path
PIPER_LENGTH_SCALE = 1.1

# Audio
SAMPLE_RATE = 44100
STATIC_GAIN = 0.12
STATIC_FADE_S = 1.0

# Robot36 picture (patch)
PICTURE_PLAY_S = 17.0
PICTURE_CAP_S = 25.0
PICTURE_W, PICTURE_H = 320, 240

# HUD
HUD_AMBER = (255, 176, 0)
HUD_DIM = (110, 76, 0)
HUD_BG = (0, 0, 0)
