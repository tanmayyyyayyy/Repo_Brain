#!/usr/bin/env python3
"""
scripts/make_demo_gif.py
Assembles a lightweight animated demonstration GIF from high-resolution screenshots.
Shows the complete RepoBrain governance flow:
  1. Blocked Review (Scenario A: Protected path, AWS key, prompt injection)
  2. Optimizer Proposal (Scenario B: Tested AST rewrite, complexity reduced)
  3. Approved & Applied (Human named approval with git trailer)
  4. Audit Trail & Dynamic Tamper Detection (HMAC invalidation)
Saves output to docs/demo.gif.
"""
import os
import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = ROOT / "docs" / "screenshots"
OUTPUT_GIF = ROOT / "docs" / "demo.gif"

FRAME_FILES = [
    ("01_scenario_a_blocked.png", 2200),
    ("03_optimizer_verified.png", 2200),
    ("04_approved_and_applied.png", 2000),
    ("06_audit_tamper_detected.png", 2500),
]


def make_gif():
    images = []
    durations = []
    target_width = 1000

    print("Generating demo GIF from screenshots...")
    for filename, duration in FRAME_FILES:
        path = SCREENSHOTS_DIR / filename
        if not path.is_file():
            print(f"Error: missing screenshot {path}", file=sys.stderr)
            sys.exit(1)

        im = Image.open(path).convert("RGBA")
        # Resize maintaining aspect ratio
        aspect = im.height / im.width
        target_height = int(target_width * aspect)
        resized = im.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # Convert to P mode (palette) with dithering for compact GIF size
        palette_im = resized.convert("RGB").quantize(colors=128, method=Image.Resampling.LANCZOS)
        images.append(palette_im)
        durations.append(duration)
        print(f"  + Added frame: {filename} ({target_width}x{target_height}, {duration}ms)")

    # Save animated GIF
    images[0].save(
        OUTPUT_GIF,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )

    size_kb = OUTPUT_GIF.stat().st_size / 1024.0
    print(f"\nSuccessfully generated {OUTPUT_GIF} ({size_kb:.1f} KB, {len(images)} frames)")


if __name__ == "__main__":
    make_gif()
