"""
Shared constants used across the bot.
"""

# ---------------------------------------------------------------------------
# Patch format magic bytes
# ---------------------------------------------------------------------------
IPS_HEADER = b"PATCH"          # 5 bytes
IPS_EOF = b"EOF"               # 3 bytes — marks end of IPS patch
UPS_HEADER = b"UPS1"           # 4 bytes

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
IPS_MAX_OFFSET = 0x00FFFFFF     # IPS cannot patch beyond 16 MiB
TELEGRAM_DOWNLOAD_LIMIT = 20 * 1024 * 1024   # 20 MB
TELEGRAM_UPLOAD_LIMIT = 50 * 1024 * 1024     # 50 MB

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
