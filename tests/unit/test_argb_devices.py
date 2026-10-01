"""
File:   test_argb_devices.py
Brief:  Tests for the ARGB device definition library and layout checks.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from luminaflowui.argb.devices import (
    DeviceLibrary,
    parse_definition,
    validate_with_library,
)
from luminaflowui.argb.schema import (
    ArgbDevice,
    ArgbHeader,
    ArgbLayer,
    ArgbLayout,
    MaskSpec,
)
from luminaflowui.exceptions import ArgbError

MINIMAL_YAML = """\
id: mini
name: Mini Bar
size: [30, 10]
leds:
  - type: rect
    rect: [0, 0, 8, 8]
  - type: circle
    center: [20, 5]
    radius: 3
"""


def _layout(devices: list[ArgbDevice], headers: list[ArgbHeader],
            layers: list[ArgbLayer] | None = None) -> ArgbLayout:
    """Assemble a layout from parts."""
    return ArgbLayout(
        headers=headers, devices=devices, layers=layers or []
    )


def _device(device_id: str, definition: str, header_id: str = "h1") -> ArgbDevice:
    """Make a device instance referencing a definition."""
    return ArgbDevice(id=device_id, device=definition, header_id=header_id, x=0, y=0)


# ---------------------------------------------------------------------------
# Definition parsing
# ---------------------------------------------------------------------------


def test_minimal_definition_parses() -> None:
    """A valid YAML definition parses with derived LED count."""
    definition = parse_definition(MINIMAL_YAML)
    assert definition.id == "mini"
    assert definition.led_count == 2
    assert definition.center() == (15.0, 5.0)


def test_led_count_is_shape_list() -> None:
    """LED count comes from the shape list, nothing else."""
    definition = parse_definition(MINIMAL_YAML)
    assert definition.led_count == len(definition.leds)


def test_unknown_led_shape_rejected() -> None:
    """LED shapes discriminate on type; unknown kinds are rejected."""
    with pytest.raises(ArgbError, match="Invalid device definition"):
        parse_definition(MINIMAL_YAML + "  - type: blob\n    rect: [0, 0, 1, 1]\n")


def test_empty_led_list_rejected() -> None:
    """A definition needs at least one LED shape."""
    with pytest.raises(ArgbError, match="Invalid device definition"):
        parse_definition("id: mini\nname: Mini\nleds: []\n")


def test_degenerate_rect_rejected() -> None:
    """Rect shapes need positive width and height."""
    with pytest.raises(ArgbError, match="positive"):
        parse_definition("id: mini\nleds:\n  - type: rect\n    rect: [0, 0, 0, 5]\n")


def test_bad_id_rejected() -> None:
    """Ids must be file-name-safe slugs."""
    with pytest.raises(ArgbError, match="Invalid device definition"):
        parse_definition("id: My Device!\nleds:\n  - type: rect\n"
                         "    rect: [0, 0, 1, 1]\n")


def test_bad_decor_color_rejected() -> None:
    """Decor colors follow the same hex pattern as everywhere else."""
    with pytest.raises(ArgbError, match="Invalid device definition"):
        parse_definition(
            "id: mini\nleds:\n  - type: rect\n    rect: [0, 0, 1, 1]\n"
            "decor:\n  - type: circle\n    center: [5, 5]\n    radius: 3\n"
            "    fill_color: red\n"
        )


# ---------------------------------------------------------------------------
# DeviceLibrary
# ---------------------------------------------------------------------------


def test_library_seeds_builtin_devices(tmp_path: Path) -> None:
    """A fresh library directory receives the bundled example devices."""
    library = DeviceLibrary(tmp_path / "devices")
    ids = [definition.id for definition in library.list()]
    assert {"strip", "ring", "dual-ring-fan"} <= set(ids)


def test_library_save_reload_delete(tmp_path: Path) -> None:
    """Saved definitions persist to disk and can be removed again."""
    library = DeviceLibrary(tmp_path / "devices")
    library.save_yaml(MINIMAL_YAML)
    assert (tmp_path / "devices" / "mini.yaml").exists()
    library.reload()
    assert library.get("mini") is not None
    assert "leds:" in library.source("mini")
    library.delete("mini")
    assert library.get("mini") is None
    assert not (tmp_path / "devices" / "mini.yaml").exists()


def test_library_save_id_mismatch_rejected(tmp_path: Path) -> None:
    """PUT-style saves must keep the definition id unchanged."""
    library = DeviceLibrary(tmp_path / "devices")
    with pytest.raises(ArgbError, match="does not match"):
        library.save_yaml(MINIMAL_YAML, expected_id="other")


def test_library_broken_file_skipped(tmp_path: Path) -> None:
    """One broken YAML file does not take the rest of the library down."""
    devices = tmp_path / "devices"
    devices.mkdir()
    (devices / "broken.yaml").write_text("id: [broken\n", encoding="utf-8")
    (devices / "mini.yaml").write_text(MINIMAL_YAML, encoding="utf-8")
    library = DeviceLibrary(devices)
    ids = [d.id for d in library.list()]
    assert "mini" in ids
    assert "broken" not in ids


def test_library_id_filename_mismatch_skipped(tmp_path: Path) -> None:
    """A definition whose id does not match its file stem is ignored."""
    devices = tmp_path / "devices"
    devices.mkdir()
    (devices / "other.yaml").write_text(MINIMAL_YAML, encoding="utf-8")
    library = DeviceLibrary(devices)
    ids = [d.id for d in library.list()]
    assert "other" not in ids
    assert "mini" not in ids


# ---------------------------------------------------------------------------
# Layout validation against the library
# ---------------------------------------------------------------------------


def _mini_library(tmp_path: Path) -> DeviceLibrary:
    """A library with the minimal two-LED definition installed."""
    library = DeviceLibrary(tmp_path / "devices")
    library.save_yaml(MINIMAL_YAML)
    return library


def test_resolve_led_counts(tmp_path: Path) -> None:
    """Counts resolve from the referenced definitions."""
    library = _mini_library(tmp_path)
    layout = _layout(
        [_device("d1", "mini"), _device("d2", "mini")],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1", "d2"])],
    )
    counts = validate_with_library(layout, library)
    assert counts == {"d1": 2, "d2": 2}


def test_unknown_definition_rejected(tmp_path: Path) -> None:
    """Instances referencing missing definitions fail with a clear error."""
    library = DeviceLibrary(tmp_path / "devices")
    layout = _layout([_device("d1", "ghost")],
                     [ArgbHeader(id="h1", zone_index=0, devices=["d1"])])
    with pytest.raises(ArgbError, match="unknown device definitions"):
        validate_with_library(layout, library)


def test_chain_overflow_rejected(tmp_path: Path) -> None:
    """A chain needing more LEDs than the zone provides is rejected."""
    library = _mini_library(tmp_path)
    layout = _layout(
        [_device("d1", "mini")],
        [ArgbHeader(id="h1", zone_index=0, size=1, devices=["d1"])],
    )
    with pytest.raises(ArgbError, match="chain needs"):
        validate_with_library(layout, library)


def test_mask_run_out_of_range_rejected(tmp_path: Path) -> None:
    """Mask runs beyond the device LED count are rejected."""
    library = _mini_library(tmp_path)
    layer = ArgbLayer(
        id="l1",
        effect={"type": "fill"},
        mask=MaskSpec(all=False, runs={"d1": [(0, 99)]}),
    )
    layout = _layout(
        [_device("d1", "mini")],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    with pytest.raises(ArgbError, match="out of range"):
        validate_with_library(layout, library)


def test_mask_run_inverted_rejected(tmp_path: Path) -> None:
    """Mask runs with start > end are rejected."""
    library = _mini_library(tmp_path)
    layer = ArgbLayer(
        id="l1",
        effect={"type": "fill"},
        mask=MaskSpec(all=False, runs={"d1": [(5, 2)]}),
    )
    layout = _layout(
        [_device("d1", "mini")],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    with pytest.raises(ArgbError, match="inverted"):
        validate_with_library(layout, library)


def test_per_corner_rect_radius_parses() -> None:
    """Rect radius accepts one number or a [tl, tr, br, bl] list."""
    definition = parse_definition(
        "id: mini\nleds:\n  - type: rect\n    rect: [0, 0, 8, 8]\n"
        "    radius: [5, 5, 0, 0]\n"
    )
    assert definition.leds[0].radius == (5.0, 5.0, 0.0, 0.0)
    single = parse_definition(
        "id: mini\nleds:\n  - type: rect\n    rect: [0, 0, 8, 8]\n    radius: 3\n"
    )
    assert single.leds[0].radius == 3.0


def test_bad_per_corner_radius_rejected() -> None:
    """Negative radii and lists that are not 4 long fail validation."""
    with pytest.raises(ArgbError, match="Invalid device definition"):
        parse_definition(
            "id: mini\nleds:\n  - type: rect\n    rect: [0, 0, 8, 8]\n"
            "    radius: [5, 5, 0]\n"
        )
    with pytest.raises(ArgbError, match="Invalid device definition"):
        parse_definition(
            "id: mini\nleds:\n  - type: rect\n    rect: [0, 0, 8, 8]\n"
            "    radius: [5, 5, -2, 0]\n"
        )
