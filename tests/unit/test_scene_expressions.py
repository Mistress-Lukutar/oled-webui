"""
File:   test_scene_expressions.py
Brief:  Unit tests for the safe expression evaluator and easing curves.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import math

import pytest

from luminaflowui.exceptions import SceneError
from luminaflowui.scene.expressions import Expression, apply_easing


def test_arithmetic_and_precedence() -> None:
    assert Expression("2 + 3 * 4").evaluate() == pytest.approx(14.0)


def test_variables_and_functions() -> None:
    result = Expression("240 + 8 * sin(2 * pi * 0.25 * t)").evaluate({"t": 1.0})
    assert result == pytest.approx(240.0 + 8.0 * math.sin(math.pi / 2.0))


def test_clamp_and_nested_calls() -> None:
    assert Expression("clamp(v, 0, 10)").evaluate({"v": 42.0}) == 10.0
    assert Expression("max(min(5, 3), 1)").evaluate() == 3.0


def test_unary_and_constants() -> None:
    assert Expression("-e + 3").evaluate() == pytest.approx(3.0 - math.e)


def test_unknown_variable_raises() -> None:
    with pytest.raises(SceneError):
        Expression("2 * bogus").evaluate()


def test_string_constant_rejected() -> None:
    with pytest.raises(SceneError):
        Expression("'evil'")


def test_attribute_access_rejected() -> None:
    with pytest.raises(SceneError):
        Expression("t.__class__")


def test_non_whitelisted_call_rejected() -> None:
    with pytest.raises(SceneError):
        Expression("__import__('os')")


def test_keyword_arguments_rejected() -> None:
    with pytest.raises(SceneError):
        Expression("clamp(x=1, lo=0, hi=2)")


def test_syntax_error_raises() -> None:
    with pytest.raises(SceneError):
        Expression("2 +* 3")


def test_apply_easing_endpoints() -> None:
    for name in ("linear", "ease-out-cubic", "ease-out-bounce"):
        assert apply_easing(name, 0.0) == pytest.approx(0.0)
        assert apply_easing(name, 1.0) == pytest.approx(1.0)


def test_apply_easing_monotonic_for_cubic() -> None:
    previous = 0.0
    for step in range(1, 11):
        value = apply_easing("ease-out-cubic", step / 10.0)
        assert value >= previous
        previous = value


def test_unknown_easing_raises() -> None:
    with pytest.raises(SceneError):
        apply_easing("ease-out-warp", 0.5)
