"""File:   test_expr_eval_port.py
Brief:  Cross-check the TS expression port against the Python evaluator.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2

Bundles the TS module with esbuild (via its JS API) and runs it under
node, comparing results with this file's Python reference values.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
CASES: list[tuple[str, float, float]] = [
    # (expression, t, expected)
    ("8 * sin(2 * pi * 0.25 * t)", 0.3, 8 * math.sin(2 * math.pi * 0.25 * 0.3)),
    ("240 + 8 * sin(2 * pi * t)", 0.0, 240.0),
    ("10 * sin(1.5 * t)", 1.0, 10 * math.sin(1.5)),
    ("t // 2", 5.0, 2.0),
    ("t % 3", 7.0, 1.0),
    ("2 ** 10", 0.0, 1024.0),
    ("-2 ** 2", 0.0, -4.0),
    ("2 ** -1", 0.0, 0.5),
    ("clamp(5, 0, 3)", 0.0, 3.0),
    ("floor(4.7)", 0.0, 4.0),
    ("ceil(4.2)", 0.0, 5.0),
    ("round(4.5)", 0.0, 4.0),
    ("round(3.5)", 0.0, 4.0),
    ("min(3, 1, 2)", 0.0, 1.0),
    ("max(3, 1, 2)", 0.0, 3.0),
    ("abs(-5)", 0.0, 5.0),
    ("sqrt(9)", 0.0, 3.0),
    ("1e-3 + 1", 0.0, 1.001),
    ("tau", 0.0, math.tau),
    ("v * 2 + t", 1.5, 11.5),
    ("(2 + 3) * 4", 0.0, 20.0),
    ("7 // 2 * 2 + 1", 0.0, 7.0),
]

NODE_RUNNER = r"""
import { pathToFileURL } from 'node:url';
const esbuild = await import(pathToFileURL(process.argv[5]).href);
const out = process.argv[2];
esbuild.buildSync({
  entryPoints: [process.argv[3]],
  bundle: true,
  format: 'esm',
  outfile: out,
  logLevel: 'silent',
});
const { Expression } = await import(pathToFileURL(out).href);
const cases = JSON.parse(process.argv[4]);
for (const [src, t] of cases) {
  const value = new Expression(src).evaluate({ t, dt: 0.05, v: 5 });
  console.log(JSON.stringify({ src, v: value }));
}
"""


def test_ts_expression_port_matches_python(tmp_path: Path) -> None:
    bundle = tmp_path / "expr-eval.mjs"
    runner = tmp_path / "runner.mjs"
    runner.write_text(NODE_RUNNER, encoding="utf-8")
    payload = json.dumps([(src, t) for src, t, _ in CASES])
    proc = subprocess.run(
        [
            "node",
            str(runner),
            str(bundle),
            str(FRONTEND / "src" / "scene-editor" / "exprEval.ts"),
            payload,
            str(FRONTEND / "node_modules" / "esbuild" / "lib" / "main.js"),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=FRONTEND,
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    assert len(lines) == len(CASES)
    for line, (src, _t, expected) in zip(lines, CASES):
        got = json.loads(line)["v"]
        assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-9), (
            f"{src}: python={expected} ts={got}"
        )
