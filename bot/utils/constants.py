"""
Shared constants used across the bot.
"""

# ---------------------------------------------------------------------------
# Patch format magic bytes
# ---------------------------------------------------------------------------
IPS_HEADER = b"PATCH"          # 5 bytes
IPS_EOF = b"EOF"               # 3 bytes — marks end of IPS patch
UPS_HEADER = b"UPS1"           # 4 bytes
BPS_HEADER = b"BPS1"           # 4 bytes

# Supported patch file extensions
SUPPORTED_EXTENSIONS = {"ips", "ups", "bps"}

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
IPS_MAX_OFFSET = 0x00FFFFFF     # IPS cannot patch beyond 16 MiB
TELEGRAM_DOWNLOAD_LIMIT = 20 * 1024 * 1024   # 20 MB (standard Bot API)
TELEGRAM_UPLOAD_LIMIT = 50 * 1024 * 1024     # 50 MB (standard Bot API)
LOCAL_API_DOWNLOAD_LIMIT = 2000 * 1024 * 1024  # ~2 GB (local Bot API)
LOCAL_API_UPLOAD_LIMIT = 2000 * 1024 * 1024    # ~2 GB (local Bot API)

# Timeouts (seconds)
FILE_DOWNLOAD_TIMEOUT = 120
FILE_UPLOAD_TIMEOUT = 120
API_CALL_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Progress bar characters
# ---------------------------------------------------------------------------
BAR_FILLED = "█"
BAR_EMPTY = "░"

# ---------------------------------------------------------------------------
# Default caption template
# ---------------------------------------------------------------------------
DEFAULT_CAPTION = (
    "📦 **{filename}**\n"
    "📏 Size: {filesize}\n"
    "🎮 ROM: {romname}\n"
    "🔧 Patch: {patchtype}\n"
    "⏱ Time: {time}"
)

# ---------------------------------------------------------------------------
# Emoji / UI tokens
# ---------------------------------------------------------------------------
EMOJI_IPS = "📋"
EMOJI_UPS = "📦"
EMOJI_CHECK = "✅"
EMOJI_CROSS = "❌"
EMOJI_GEAR = "⚙️"
EMOJI_DOWNLOAD = "📥"
EMOJI_UPLOAD = "📤"
EMOJI_WRENCH = "🔧"
EMOJI_WAIT = "⏳"
EMOJI_GAME = "🎮"
EMOJI_FOLDER = "📂"
EMOJI_PLAY = "▶️"
EMOJI_CANCEL = "❌"
EMOJI_PING = "🏓"
EMOJI_BROADCAST = "📡"
EMOJI_CHART = "📊"
EMOJI_THUMB = "🖼"
EMOJI_PENCIL = "✏️"
