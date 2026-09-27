"""
File:   __init__.py
Brief:  Scene subsystem: declarative display layouts with live widgets.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from oled_webui.exceptions import SceneError
from oled_webui.scene.loader import load_scene, load_scene_from_text
from oled_webui.scene.runner import SceneRenderer
from oled_webui.scene.schema import SceneDocument

__all__ = [
    "SceneDocument",
    "SceneError",
    "SceneRenderer",
    "load_scene",
    "load_scene_from_text",
]
