#!/usr/bin/env python3
"""
Automated WCAG 2.1 AA contrast checker for RepoBrain design tokens.

Tokens are parsed directly from repobrain/web/index.html so the report cannot drift
away from the shipped palette. The checker covers:

  * every text / syntax token against every surface background
  * every UI border and focus ring against every surface background
  * text on filled controls (accent, warning, pass, block, AI)
  * tinted badge text on its composited signal background

Text requires >= 4.5:1, UI components require >= 3.0:1.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from repobrain.server import find_index_html
INDEX_PATH = find_index_html()

SURFACES = [
    ("App", "bg-app"),
    ("Rail", "bg-rail"),
    ("Surface", "bg-surface"),
    ("Raised", "bg-surface-raised"),
    ("Hover", "bg-surface-hover"),
    ("Input", "bg-input"),
]

TEXT_TOKENS = [
    "text-primary",
    "text-secondary",
    "text-muted",
    "brand-accent",
    "signal-pass",
    "signal-warn",
    "signal-block",
    "signal-ai",
    "syn-keyword",
    "syn-string",
    "syn-comment",
    "syn-number",
]

UI_TOKENS = [
    "border-default",
    "border-strong",
    "brand-accent",
    "signal-pass-border",
    "signal-warn-border",
    "signal-block-border",
    "signal-ai-border",
]

FILLED_CONTROLS = [
    "brand-accent",
    "brand-accent-hover",
    "signal-pass",
    "signal-warn",
    "signal-block",
    "signal-ai",
]

BADGES = [
    ("signal-pass", "signal-pass-bg"),
    ("signal-warn", "signal-warn-bg"),
    ("signal-block", "signal-block-bg"),
    ("signal-ai", "signal-ai-bg"),
]

THEME_BLOCK_RE = re.compile(
    r"(?P<selector>:root|\[data-theme=[\"']light[\"']\])\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)
TOKEN_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
HEX_RE = re.compile(r"^#([0-9a-fA-F]{6})$")
RGB_RE = re.compile(r"^rgba?\(([^)]+)\)$")


def parse_palettes(path=INDEX_PATH):
    """Return {'dark': {token: value}, 'light': {token: value}} from the live CSS."""
    html = open(path, encoding="utf-8").read()
    palettes = {}
    for match in THEME_BLOCK_RE.finditer(html):
        selector = match.group("selector")
        theme = "dark" if selector == ":root" else "light"
        tokens = {name: value.strip() for name, value in TOKEN_RE.findall(match.group("body"))}
        if tokens:
            palettes[theme] = tokens
    missing = {"dark", "light"} - set(palettes)
    if missing:
        raise RuntimeError(f"Could not parse theme tokens from {path}: missing {sorted(missing)}")
    return palettes


def parse_color(value):
    value = value.strip()
    match = HEX_RE.match(value)
    if match:
        h = match.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    match = RGB_RE.match(value)
    if match:
        parts = [p.strip() for p in match.group(1).split(",")]
        if len(parts) not in (3, 4):
            raise ValueError(f"Unsupported rgb color: {value}")
        channels = [int(round(float(p[:-1]) * 2.55)) if p.endswith("%") else int(float(p)) for p in parts[:3]]
        alpha = float(parts[3]) if len(parts) == 4 else 1.0
        return tuple(channels) + (alpha,)
    raise ValueError(f"Unsupported color value: {value}")


def to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb[:3])


def composite(fg, bg):
    fg = parse_color(fg)
    bg = parse_color(bg)
    a = fg[3]
    return to_hex(tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3)))


def rel_luminance(rgb):
    def channel(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = [channel(v) for v in rgb[:3]]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(c1, c2):
    l1 = rel_luminance(parse_color(c1))
    l2 = rel_luminance(parse_color(c2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def ratio_rows(tokens, names, target, surface_values):
    rows = []
    for name in names:
        color = tokens[f"--{name}"]
        ratios = [contrast(color, value) for _, value in surface_values]
        rows.append((name, color, ratios, all(r >= target for r in ratios)))
    return rows


def ratio_table(title, rows, target, surface_names=("App", "Rail", "Surface", "Raised", "Hover", "Input")):
    header = "| Token | Hex | " + " | ".join(surface_names) + f" | Target | Status |"
    divider = "|---|---|" + "|".join(["---"] * len(surface_names)) + "---|---|"
    lines = [f"**{title}**", "", header, divider]
    for name, color, ratios, passed in rows:
        cells = [f"{r:.2f}:1" for r in ratios]
        status = "PASS" if passed else "FAIL"
        lines.append(f"| `--{name}` | `{color}` | " + " | ".join(cells) + f" | {target}:1 | {status} |")
    return lines


def run_check():
    palettes = parse_palettes()
    all_passed = True
    markdown_lines = []

    for theme, label in [
        ("dark", "Dark Theme (Mission Control)"),
        ("light", "Light Theme (Instrument Paper)"),
    ]:
        tokens = palettes[theme]
        surface_values = [(name, tokens[f"--{token}"]) for name, token in SURFACES]
        markdown_lines.append(f"\n### {label}\n")

        text_rows = ratio_rows(tokens, TEXT_TOKENS, 4.5, surface_values)
        ui_rows = ratio_rows(tokens, UI_TOKENS, 3.0, surface_values)

        markdown_lines.extend(ratio_table("Text & syntax tokens vs every surface", text_rows, 4.5))
        markdown_lines.append("")
        markdown_lines.extend(ratio_table("UI component borders / focus ring vs every surface", ui_rows, 3.0))
        markdown_lines.append("")

        markdown_lines.append("**Text on filled controls**")
        markdown_lines.append("")
        markdown_lines.append("| Text | Fill | Ratio | Target | Status |")
        markdown_lines.append("|---|---|---|---|---|")
        inverse = tokens["--text-inverse"]
        for fill in FILLED_CONTROLS:
            ratio = contrast(inverse, tokens[f"--{fill}"])
            passed = ratio >= 4.5
            all_passed = all_passed and passed
            markdown_lines.append(
                f"| `--text-inverse` | `--{fill}` (`{tokens[f'--{fill}']}`) | {ratio:.2f}:1 | 4.5:1 | {'PASS' if passed else 'FAIL'} |"
            )

        markdown_lines.append("")
        markdown_lines.append("**Tinted badge text on composited signal backgrounds**")
        markdown_lines.append("")
        markdown_lines.append("| Text | Badge bg | App | Rail | Surface | Raised | Hover | Input | Target | Status |")
        markdown_lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for text_token, bg_token in BADGES:
            text_color = tokens[f"--{text_token}"]
            bg_color = tokens[f"--{bg_token}"]
            ratios = [contrast(text_color, composite(bg_color, value)) for _, value in surface_values]
            passed = all(r >= 4.5 for r in ratios)
            all_passed = all_passed and passed
            cells = [f"{r:.2f}:1" for r in ratios]
            markdown_lines.append(
                f"| `--{text_token}` | `--{bg_token}` | " + " | ".join(cells) +
                f" | 4.5:1 | {'PASS' if passed else 'FAIL'} |"
            )

        for _, _, ratios, passed in text_rows + ui_rows:
            all_passed = all_passed and passed

    report = "\n".join(markdown_lines)
    print(report)

    if all_passed:
        print("\n=======================================================")
        print("ALL CONTRAST CHECKS PASSED WCAG 2.1 AA SPECIFICATIONS!")
        print("=======================================================")
        return 0, report

    print("\nFAILED: Some color token pairs did not meet WCAG AA requirements.")
    return 1, report


if __name__ == "__main__":
    code, _ = run_check()
    sys.exit(code)
