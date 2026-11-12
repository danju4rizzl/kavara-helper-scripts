"""Application constants and terminal style codes."""

APP_NAME = "Kavara Audio Enhancer"
VERSION = "1.6.0"

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts"}

MIN_PLAYBACK_SPEED = 0.25
MAX_PLAYBACK_SPEED = 4.0

MIN_LUFS_TARGET = -70.0
MAX_LUFS_TARGET = -5.0

SAMPLE_RATE = 44100  # Hz -- standard CD-quality sample rate

CHUNK_DURATION_SECONDS = 180.0  # 3 minutes per chunk — optimal for AI accuracy & parallel upload
DEFAULT_MAX_WORKERS = 4         # Default number of concurrent worker threads for AI chunk analysis

GEMINI_MODEL_LABEL = "Gemini 3.5 Transcribe"
DEFAULT_GEMINI_MODEL = "gemini-3.5-transcribe"

# Filler / repeated-phrase detection (applied to word-timed transcripts)
# Matches stretched spellings: um, umm, uhmmm, uh, uhhh, er, erm, ah, ahh, hmm, mmm, eh
FILLER_PATTERN = r"u+h*m+h*|u+h+|e+r+m*|a+h+m*|e+h+|h+m+|m{2,}"
MAX_REPEAT_PHRASE_WORDS = 8     # Longest restarted phrase we look for
MAX_REPEAT_GAP_SECONDS = 1.5    # Longer pause between two identical phrases = deliberate, keep both

# Restarted sentences ("we're going to use another... we're going to use a ...")
RESTART_MIN_OPENER_WORDS = 3    # Shared opening words needed to call it a restart (if the first try was unfinished)
RESTART_MAX_SPAN_SECONDS = 12.0 # Max duration of the abandoned attempt
RESTART_MAX_SPAN_WORDS = 16     # Max length of the abandoned attempt
RESTART_MAX_GAP_SECONDS = 3.0   # Max pause before the restart

# Subtitle line building from word timings
SUBTITLE_MAX_WORDS = 12
SUBTITLE_MAX_SECONDS = 6.0
SUBTITLE_BREAK_GAP_SECONDS = 0.7

# Terminal Styling Colors & Formatting (ANSI with Colorama support)
STYLE_HEADER = "\033[1;36m"   # Bold Cyan
STYLE_SUCCESS = "\033[1;32m"  # Bold Green
STYLE_WARNING = "\033[1;33m"  # Bold Yellow
STYLE_ERROR = "\033[1;31m"    # Bold Red
STYLE_ACCENT = "\033[1;35m"   # Bold Magenta
STYLE_BOLD = "\033[1m"        # Bold
STYLE_DIM = "\033[2m"         # Dim
STYLE_RESET = "\033[0m"       # Reset

LOUDNORM_TRUE_PEAK = -1.5  # dBTP ceiling used for EBU R128 loudness normalization
LOUDNORM_LRA = 11.0        # Target loudness range (LU)
ATEMPO_MIN_FACTOR = 0.5    # Per-filter limits guaranteed by every FFmpeg version
ATEMPO_MAX_FACTOR = 2.0

# Cut validation & smoothing
MIN_CUT_SECONDS = 0.05          # Ignore cuts shorter than this (likely noise / rounding)
MAX_CUT_FRACTION = 0.8          # If cuts would remove more than this share of the file, assume a bad AI result
DECLICK_FADE_SECONDS = 0.01     # Fade applied at every cut boundary to avoid audible clicks

# Local silence detection (FFmpeg silencedetect)
DEFAULT_SILENCE_THRESHOLD_DB = -35.0
SILENCE_MIN_DURATION = 0.5      # Only silences at least this long are candidates
SILENCE_KEEP_PADDING = 0.15     # Seconds of silence kept on each side so pauses stay natural
