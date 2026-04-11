"""
Unicode progress-bar renderer.
"""

from bot.utils.constants import BAR_FILLED, BAR_EMPTY


def render_progress(percent: int, width: int = 20) -> str:
    """
    Return a unicode progress bar string.

    >>> render_progress(45)
    '[█████████░░░░░░░░░░░] 45%'
    """
    percent = max(0, min(100, percent))
    filled = int(width * percent / 100)
    bar = BAR_FILLED * filled + BAR_EMPTY * (width - filled)
    return f"[{bar}] {percent}%"


def stage_text(stage: str, percent: int) -> str:
    """Combine a stage label with a progress bar."""
    bar = render_progress(percent)
    return f"{stage}\n{bar}"
