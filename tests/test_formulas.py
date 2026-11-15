"""Guard the TeX in the page against the mistake that broke it once.

The formulas are written with String.raw, where a doubled backslash stays doubled
and reaches KaTeX as two characters, so every command silently renders as text. A
test that only checks the page loads would not catch it, so this one reads the TeX
out of the source and checks the shape of every command.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "web" / "js" / "app.js"


def formulas() -> dict[str, str]:
    source = APP.read_text()
    start = source.index("const FORMULAS = {")
    end = source.index("};", start)
    block = source[start:end]
    return dict(re.findall(r"(\w+):\s*\{[^}]*?tex:\s*String\.raw`([^`]*)`", block, re.S))


def test_every_formula_is_present() -> None:
    found = formulas()
    assert len(found) >= 8, f"expected at least 8 formulas, found {len(found)}"


def test_no_doubled_backslash() -> None:
    """String.raw keeps a doubled backslash doubled, which KaTeX reads as a line
    break followed by text rather than as a command."""
    for name, tex in formulas().items():
        assert "\\\\" not in tex, f"{name} has a doubled backslash: {tex}"


def test_every_command_is_known() -> None:
    """Every backslash command must be one KaTeX supports, and must be followed by
    a letter or a symbol rather than by another backslash."""
    known = {
        "frac", "quad", "text", "Delta", "times", "sigma", "operatorname",
        "mathrm", "mu", "alpha", "cos", "delta", "max", "min", "sum", "int",
        "left", "right", "cdot", "pm", "approx", "sim", "propto", "log", "exp",
    }
    for name, tex in formulas().items():
        for command in re.findall(r"\\([A-Za-z]+)", tex):
            assert command in known, f"{name} uses an unknown command: \\{command}"


def test_braces_balance() -> None:
    for name, tex in formulas().items():
        assert tex.count("{") == tex.count("}"), f"{name} has unbalanced braces: {tex}"
