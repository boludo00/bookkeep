"""Browser fingerprint profile management for bypass stealth."""

import random
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

COMMON_RESOLUTIONS = [
    (1920, 1080, 0.35),
    (1366, 768, 0.18),
    (1536, 864, 0.10),
    (2560, 1440, 0.08),
    (1280, 720, 0.07),
    (1440, 900, 0.06),
    (1600, 900, 0.05),
    (1280, 800, 0.04),
    (1680, 1050, 0.04),
    (1920, 1200, 0.03),
]

# Current screen size (module-level singleton)
_current_screen_size: Optional[tuple[int, int]] = None


def get_random_screen_size() -> tuple[int, int]:
    """Generate a random screen size using weighted distribution."""
    global _current_screen_size
    if _current_screen_size is None:
        _current_screen_size = _generate_screen_size()
        logger.debug("generated_screen_size", width=_current_screen_size[0], height=_current_screen_size[1])
    return _current_screen_size


def rotate_screen_size() -> tuple[int, int]:
    """Rotate to a new screen size."""
    global _current_screen_size
    old_size = _current_screen_size
    _current_screen_size = _generate_screen_size()
    width, height = _current_screen_size

    if old_size:
        logger.info("rotated_screen_size", old=f"{old_size[0]}x{old_size[1]}", new=f"{width}x{height}")
    else:
        logger.info("generated_screen_size", width=width, height=height)

    return _current_screen_size


def clear_screen_size() -> None:
    """Clear the current screen size."""
    global _current_screen_size
    _current_screen_size = None


def _generate_screen_size() -> tuple[int, int]:
    """Generate a random screen size using weighted distribution."""
    resolutions = [(w, h) for w, h, _ in COMMON_RESOLUTIONS]
    weights = [weight for _, _, weight in COMMON_RESOLUTIONS]
    return random.choices(resolutions, weights=weights)[0]
