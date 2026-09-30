"""
File:   expressions.py
Brief:  Safe numeric expression evaluator and easing functions for scenes.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable, Mapping

from oled_webui.exceptions import SceneError

# Binary operators allowed in scene expressions.
_BIN_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Unary operators allowed in scene expressions.
_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Named functions allowed in scene expressions.
_FUNCTIONS: dict[str, Callable[..., float]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "min": min,
    "max": max,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "round": round,
    "clamp": lambda x, lo, hi: max(lo, min(hi, x)),
}

# Named constants allowed in scene expressions.
_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "tau": math.tau,
    "e": math.e,
}


class Expression:
    """Pre-compiled arithmetic expression evaluated against numeric variables.

    Only whitelisted arithmetic, function calls and constants are permitted;
    anything else (names, attributes, strings, lambdas, ...) raises
    :class:`SceneError` at compile time.
    """

    def __init__(self, source: str) -> None:
        """Compile the expression source.

        Args:
            source: Expression text, e.g. ``"240 + 8 * sin(2 * pi * t)"``.

        Raises:
            SceneError: If the source cannot be parsed or contains
                disallowed constructs.
        """
        self._source = source
        try:
            tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:
            raise SceneError(f"Invalid expression {source!r}: {exc}") from exc
        self._check(tree.body)
        self._tree: ast.expr = tree.body

    @staticmethod
    def _check(node: ast.expr) -> None:
        """Recursively validate the AST against the whitelist.

        Args:
            node: AST node to validate.

        Raises:
            SceneError: If the node (or a child) is disallowed.
        """
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise SceneError(f"Only numeric constants allowed: {node.value!r}")
            return
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            Expression._check(node.left)
            Expression._check(node.right)
            return
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            Expression._check(node.operand)
            return
        if isinstance(node, ast.Call):
            func = node.func
            if not isinstance(func, ast.Name) or func.id not in _FUNCTIONS:
                raise SceneError("Only whitelisted function calls are allowed")
            if node.keywords:
                raise SceneError("Keyword arguments are not allowed")
            for arg in node.args:
                Expression._check(arg)
            return
        if isinstance(node, ast.Name):
            if node.id not in _CONSTANTS:
                # Unknown names are permitted at compile time; they must be
                # supplied as variables at evaluation time.
                return
            return
        raise SceneError(f"Disallowed construct in expression: {type(node).__name__}")

    def evaluate(self, variables: Mapping[str, float] | None = None) -> float:
        """Evaluate the expression with the given variables.

        Args:
            variables: Numeric variables such as ``t``, ``dt`` or ``v``.

        Returns:
            Numeric result.

        Raises:
            SceneError: If an unknown variable is referenced or division
                by zero occurs.
        """
        scope: dict[str, float] = dict(_CONSTANTS)
        if variables:
            scope.update(variables)
        try:
            result = self._eval(self._tree, scope)
        except NameError as exc:
            raise SceneError(f"Unknown variable in {self._source!r}: {exc}") from exc
        except ZeroDivisionError as exc:
            raise SceneError(f"Division by zero in {self._source!r}") from exc
        return result

    def _eval(self, node: ast.expr, scope: dict[str, float]) -> float:
        """Recursively evaluate a validated AST node.

        Args:
            node: AST node to evaluate.
            scope: Variable scope.

        Returns:
            Numeric result of the node.

        Raises:
            NameError: If a variable is not present in the scope.
            ZeroDivisionError: On division by zero.
        """
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, (int, float)):
                return float(value)
            raise SceneError(  # pragma: no cover - guarded by _check
                f"Only numeric constants allowed: {value!r}"
            )
        if isinstance(node, ast.BinOp):
            left = self._eval(node.left, scope)
            right = self._eval(node.right, scope)
            return _BIN_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp):
            return _UNARY_OPS[type(node.op)](self._eval(node.operand, scope))
        if isinstance(node, ast.Call):
            func = _FUNCTIONS[node.func.id]  # type: ignore[attr-defined]
            args = [self._eval(arg, scope) for arg in node.args]
            return float(func(*args))
        if isinstance(node, ast.Name):
            if node.id in scope:
                return scope[node.id]
            raise NameError(node.id)
        raise SceneError(  # pragma: no cover - guarded by _check
            f"Disallowed construct in expression: {type(node).__name__}"
        )


def _ease_linear(t: float) -> float:
    """Linear interpolation curve."""
    return t


def _ease_in_quad(t: float) -> float:
    """Quadratic ease-in curve."""
    return t * t


def _ease_out_quad(t: float) -> float:
    """Quadratic ease-out curve."""
    return 1.0 - (1.0 - t) * (1.0 - t)


def _ease_in_out_quad(t: float) -> float:
    """Quadratic ease-in-out curve."""
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - 2.0 * (1.0 - t) * (1.0 - t)


def _ease_in_cubic(t: float) -> float:
    """Cubic ease-in curve."""
    return t * t * t


def _ease_out_cubic(t: float) -> float:
    """Cubic ease-out curve."""
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out curve."""
    if t < 0.5:
        return 4.0 * t**3
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def _ease_out_back(t: float) -> float:
    """Ease-out with slight overshoot."""
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def _ease_out_elastic(t: float) -> float:
    """Elastic ease-out curve."""
    if t in (0.0, 1.0):
        return t
    c4 = (2.0 * math.pi) / 3.0
    return float(2.0 ** (-10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0)


def _ease_out_bounce(t: float) -> float:
    """Bouncing ease-out curve."""
    n1 = 7.5625
    d1 = 2.75
    if t < 1.0 / d1:
        return n1 * t * t
    if t < 2.0 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


# Easing curves available to scene animation specs.
EASINGS: dict[str, Callable[[float], float]] = {
    "linear": _ease_linear,
    "ease-in-quad": _ease_in_quad,
    "ease-out-quad": _ease_out_quad,
    "ease-in-out-quad": _ease_in_out_quad,
    "ease-in-cubic": _ease_in_cubic,
    "ease-out-cubic": _ease_out_cubic,
    "ease-in-out-cubic": _ease_in_out_cubic,
    "ease-out-back": _ease_out_back,
    "ease-out-elastic": _ease_out_elastic,
    "ease-out-bounce": _ease_out_bounce,
}


def apply_easing(name: str, t: float) -> float:
    """Apply a named easing curve to a normalized progress value.

    Args:
        name: Easing name from :data:`EASINGS`.
        t: Progress in ``[0, 1]``.

    Returns:
        Eased progress in ``[0, 1]`` (overshoot curves may exceed it).

    Raises:
        SceneError: If the easing name is unknown.
    """
    try:
        curve = EASINGS[name]
    except KeyError as exc:
        known = ", ".join(sorted(EASINGS))
        raise SceneError(f"Unknown easing {name!r}; available: {known}") from exc
    return curve(max(0.0, min(1.0, t)))
