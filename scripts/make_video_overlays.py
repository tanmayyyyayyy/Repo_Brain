#!/usr/bin/env python3
"""Generate high-DPI transparent lower-third overlays and outro slide for RepoBrain demo video."""
import os
from PIL import Image, ImageDraw, ImageFont

OVERLAYS_DIR = "/tmp/video_overlays"
os.makedirs(OVERLAYS_DIR, exist_ok=True)

# Colors
BG_BOX = (14, 20, 30, 230)
BORDER_CYAN = (56, 189, 248, 200)
BORDER_PURPLE = (168, 85, 247, 200)
BORDER_GREEN = (52, 211, 153, 200)
BORDER_AMBER = (251, 191, 36, 200)
BORDER_RED = (248, 113, 113, 200)

TEXT_TITLE = (248, 250, 252, 255)
TEXT_SUB = (203, 213, 225, 255)
TEXT_MUTED = (148, 163, 184, 255)

# Fonts
try:
    FONT_BADGE = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 15)
    FONT_TITLE = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 24)
    FONT_SUB = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 16)
    FONT_BIG = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 44)
    FONT_BIG_SUB = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 22)
    FONT_MONO = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 18)
except Exception:
    FONT_BADGE = FONT_TITLE = FONT_SUB = FONT_BIG = FONT_BIG_SUB = FONT_MONO = ImageFont.load_default()

OVERLAYS = [
    {
        "filename": "ov1_mission_control.png",
        "badge": "MISSION CONTROL",
        "badge_color": (56, 189, 248),
        "border_color": BORDER_CYAN,
        "title": "Autonomous Governance for AI-Touched Code",
        "subtitle": "Real-time policy interception, risk scoring (97/100 Critical), and pipeline status"
    },
    {
        "filename": "ov2_shield.png",
        "badge": "SHIELD ENGINE",
        "badge_color": (248, 113, 113),
        "border_color": BORDER_RED,
        "title": "Pre-Flight Secret & Injection Blocking",
        "subtitle": "Intercepts hidden HTML comment injections, hardcoded AWS keys, and protected workflows"
    },
    {
        "filename": "ov3_diff.png",
        "badge": "INLINE DIFF INSPECTOR",
        "badge_color": (168, 85, 247),
        "border_color": BORDER_PURPLE,
        "title": "Interactive Line-Level Vulnerability Annotations",
        "subtitle": "Contextual rule badges, blast radius analysis, and AI authorship provenance"
    },
    {
        "filename": "ov4_github.png",
        "badge": "GITHUB ACTIONS CI",
        "badge_color": (56, 189, 248),
        "border_color": BORDER_CYAN,
        "title": "Automated Pull Request Enforcement & Sticky Commenting",
        "subtitle": "Enforced from trusted base branch — AI agents cannot weaken their own governance"
    },
    {
        "filename": "ov5_optimizer.png",
        "badge": "AST OPTIMIZER",
        "badge_color": (52, 211, 153),
        "border_color": BORDER_GREEN,
        "title": "Complexity Gate: Automated Guard-Clause Refactoring",
        "subtitle": "Reduces cognitive complexity 15->10 & nesting depth 4->3 with test-verified equivalency"
    },
    {
        "filename": "ov6_audit.png",
        "badge": "AUDIT LEDGER",
        "badge_color": (251, 191, 36),
        "border_color": BORDER_AMBER,
        "title": "Cryptographic Blockchain Ledger (SHA-256 HMAC)",
        "subtitle": "Tamper-evident chain of custody: modifying any block invalidates downstream hashes"
    },
    {
        "filename": "ov7_access.png",
        "badge": "ACCESSIBILITY & UX",
        "badge_color": (56, 189, 248),
        "border_color": BORDER_CYAN,
        "title": "Universal Mission Control: Light, Dark & Presenter Modes",
        "subtitle": "WCAG 2.1 AA compliant contrast ratios, keyboard shortcuts, and quick Command Palette"
    }
]

def make_lower_third(data):
    im = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # Position at bottom-left
    x, y, w, h = 60, 925, 920, 100
    r = 14

    # Background card with glow outline
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=BG_BOX, outline=data["border_color"], width=2)

    # Category Pill
    badge_text = data["badge"]
    badge_w = len(badge_text) * 9 + 26
    draw.rounded_rectangle([x + 18, y + 16, x + 18 + badge_w, y + 42], radius=6,
                           fill=(*data["badge_color"], 30), outline=(*data["badge_color"], 140), width=1)
    draw.text((x + 28, y + 20), badge_text, font=FONT_BADGE, fill=(*data["badge_color"], 255))

    # Title
    draw.text((x + 30 + badge_w, y + 17), data["title"], font=FONT_TITLE, fill=TEXT_TITLE)

    # Subtitle
    draw.text((x + 22, y + 56), data["subtitle"], font=FONT_SUB, fill=TEXT_SUB)

    path = os.path.join(OVERLAYS_DIR, data["filename"])
    im.save(path)
    print(f"Created overlay: {path}")

def make_outro_slide():
    im = Image.new("RGBA", (1920, 1080), (8, 12, 18, 255))
    draw = ImageDraw.Draw(im)

    # Decorative background grid lines
    for gx in range(0, 1920, 120):
        draw.line([(gx, 0), (gx, 1080)], fill=(20, 28, 42, 100), width=1)
    for gy in range(0, 1080, 80):
        draw.line([(0, gy), (1920, gy)], fill=(20, 28, 42, 100), width=1)

    # Central Card
    cx, cy, cw, ch = 360, 260, 1200, 560
    draw.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=24, fill=(14, 19, 27, 245),
                           outline=(56, 189, 248, 160), width=2)

    # Top Pill
    draw.rounded_rectangle([cx + 420, cy + 45, cx + 780, cy + 85], radius=20,
                           fill=(56, 189, 248, 30), outline=(56, 189, 248, 180), width=1)
    draw.text((cx + 455, cy + 54), "MISSION CONTROL VERIFIED", font=FONT_BADGE, fill=(56, 189, 248, 255))

    # Big Title
    draw.text((cx + 440, cy + 120), "RepoBrain", font=FONT_BIG, fill=(248, 250, 252, 255))

    # Slogan
    draw.text((cx + 170, cy + 205),
              "Policy, Proof and Clean Code for Repositories Touched by AI Agents",
              font=FONT_BIG_SUB, fill=(56, 189, 248, 255))

    # 3 Feature Bullets
    bullets = [
        "✓  Shield: AST Split-Secrets, Injections & Protected Paths Blocked",
        "✓  AST Optimizer: Semantic Complexity Reduction & Test-Verified Refactoring",
        "✓  Audit Chain: Cryptographic SHA-256 HMAC-Signed Tamper-Evident History",
        "✓  Native CI: GitHub Actions Integration Enforced from Trusted Base"
    ]
    by = cy + 285
    for b in bullets:
        draw.text((cx + 200, by), b, font=FONT_SUB, fill=(203, 213, 225, 255))
        by += 38

    # Repo URL
    draw.rounded_rectangle([cx + 310, cy + 475, cx + 890, cy + 520], radius=8,
                           fill=(20, 28, 42, 220), outline=(148, 163, 184, 100), width=1)
    draw.text((cx + 340, cy + 487), "github.com/tanmayyyyayyy/Repo_Brain", font=FONT_MONO, fill=(148, 163, 184, 255))

    path = os.path.join(OVERLAYS_DIR, "outro_slide.png")
    im.save(path)
    print(f"Created outro slide: {path}")

if __name__ == "__main__":
    for ov in OVERLAYS:
        make_lower_third(ov)
    make_outro_slide()
