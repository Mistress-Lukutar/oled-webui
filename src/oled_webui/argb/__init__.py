"""
File:   __init__.py
Brief:  ARGB subsystem: layouts, effect engine and OpenRGB output.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.5.1
"""

from oled_webui.argb.engine import render_layout
from oled_webui.argb.schema import ArgbLayout, default_layout
from oled_webui.argb.service import ArgbService

__all__ = [
    "ArgbLayout",
    "ArgbService",
    "default_layout",
    "render_layout",
]
