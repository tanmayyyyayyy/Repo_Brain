#!/usr/bin/env python3
"""Build edited demo video with zoom effects, trims, lower-third overlays, and outro."""
import os
import subprocess
import sys
import time

FFMPEG = "/opt/homebrew/bin/ffmpeg"
INPUT_VIDEO = "docs/demo/raw_screen_recording.mov"
CLIPS_DIR = "/tmp/demo_clips"
OVERLAYS_DIR = "/tmp/video_overlays"
FINAL_OUTPUT = "/Users/tanmayjain/Downloads/repobrain_demo_edited.mp4"
REPO_OUTPUT = "docs/demo/repobrain_demo_edited.mp4"

os.makedirs(CLIPS_DIR, exist_ok=True)
os.makedirs("docs/demo", exist_ok=True)

# Preset crop definitions on 3360x1918 raw screen
CROP_WIDE = "crop=3360:1890:0:14,scale=1920:1080"
CROP_HERO = "crop=2400:1350:400:80,scale=1920:1080"
CROP_TABLE = "crop=2400:1350:400:380,scale=1920:1080"
CROP_GH = "crop=2200:1238:400:300,scale=1920:1080"
CROP_OPT = "crop=2400:1350:450:200,scale=1920:1080"
CROP_AUDIT = "crop=2400:1350:450:150,scale=1920:1080"
CROP_PALETTE = "crop=2200:1238:550:250,scale=1920:1080"

CLIPS = [
    {
        "id": "clip_01_intro_wide",
        "ss": 9.2,
        "t": 4.8,
        "crop": CROP_WIDE,
        "overlay": "ov1_mission_control.png",
        "fade_in": True,
        "desc": "Wide Establishing Shot: Mission Control Overview"
    },
    {
        "id": "clip_02_hero_zoom",
        "ss": 14.0,
        "t": 8.0,
        "crop": CROP_HERO,
        "overlay": "ov1_mission_control.png",
        "desc": "Zoom: Blocked Verdict Banner & Critical Risk Score (97)"
    },
    {
        "id": "clip_03_shield_findings",
        "ss": 22.0,
        "t": 20.5,
        "crop": CROP_TABLE,
        "overlay": "ov2_shield.png",
        "desc": "Zoom: Shield Blocking Findings (Injection, Secret, Path)"
    },
    # (Invisible match-cut skips 42.5s - 55.5s IDE window switch)
    {
        "id": "clip_04_diff_tour",
        "ss": 55.5,
        "t": 28.5,
        "crop": CROP_TABLE,
        "overlay": "ov3_diff.png",
        "desc": "Inline File Diff Inspector & Guided Tour Step"
    },
    {
        "id": "clip_05_github_pr",
        "ss": 84.0,
        "t": 12.0,
        "crop": CROP_GH,
        "overlay": "ov4_github.png",
        "desc": "Live GitHub Actions PR Enforcement & Sticky Comment"
    },
    {
        "id": "clip_06_ast_optimizer",
        "ss": 96.0,
        "t": 18.0,
        "crop": CROP_OPT,
        "overlay": "ov5_optimizer.png",
        "desc": "AST Optimizer: Cognitive Complexity 15->10 & Nesting 4->3"
    },
    {
        "id": "clip_07_audit_ledger",
        "ss": 114.0,
        "t": 20.0,
        "crop": CROP_AUDIT,
        "overlay": "ov6_audit.png",
        "desc": "Cryptographic Audit Ledger (SHA-256 HMAC-Signed Blocks)"
    },
    {
        "id": "clip_08_accessibility",
        "ss": 134.0,
        "t": 12.5,
        "crop": CROP_PALETTE,
        "overlay": "ov7_access.png",
        "desc": "Presenter Mode, Light Theme (WCAG AA), Command Palette"
    }
]

def render_clip(idx, clip):
    out_path = os.path.join(CLIPS_DIR, f"{clip['id']}.mp4")
    print(f"\n[{idx+1}/{len(CLIPS)+1}] Rendering {clip['desc']}...")

    ov_path = os.path.join(OVERLAYS_DIR, clip["overlay"])
    has_overlay = os.path.exists(ov_path)

    # Filter graph
    # 1. crop and scale base video to 1920x1080 60fps
    # 2. apply fade-in if requested
    # 3. overlay lower-third banner
    vf = f"{clip['crop']},fps=60"
    if clip.get("fade_in"):
        vf += ",fade=t=in:st=0:d=0.8"

    if has_overlay:
        fade_out_start = min(3.8, max(2.5, clip["t"] - 1.0))
        cmd = [
            FFMPEG, "-y",
            "-ss", str(clip["ss"]),
            "-t", str(clip["t"]),
            "-i", INPUT_VIDEO,
            "-loop", "1",
            "-t", str(clip["t"]),
            "-i", ov_path,
            "-filter_complex",
            f"[0:v]{vf}[base];[1:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st={fade_out_start}:d=0.5:alpha=1[ov];[base][ov]overlay=0:0[outv]",
            "-map", "[outv]",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            out_path
        ]
    else:
        cmd = [
            FFMPEG, "-y",
            "-ss", str(clip["ss"]),
            "-t", str(clip["t"]),
            "-i", INPUT_VIDEO,
            "-vf", vf,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            out_path
        ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"Error rendering {clip['id']}:", r.stderr[-500:])
        sys.exit(1)
    print(f"  ✓ Finished {clip['id']}.mp4 ({clip['t']}s)")
    return out_path

def render_outro():
    out_path = os.path.join(CLIPS_DIR, "clip_09_outro.mp4")
    print(f"\n[{len(CLIPS)+1}/{len(CLIPS)+1}] Rendering Outro Slide...")
    slide_path = os.path.join(OVERLAYS_DIR, "outro_slide.png")
    duration = 3.5

    cmd = [
        FFMPEG, "-y",
        "-loop", "1",
        "-i", slide_path,
        "-t", str(duration),
        "-vf", "scale=1920:1080,fps=60,fade=t=in:st=0:d=0.6,fade=t=out:st=2.7:d=0.8",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        out_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("Error rendering outro slide:", r.stderr[-500:])
        sys.exit(1)
    print(f"  ✓ Finished clip_09_outro.mp4 ({duration}s)")
    return out_path

def concat_clips(clip_paths):
    print("\nConcatenating all clips into master video...")
    concat_list = os.path.join(CLIPS_DIR, "concat_list.txt")
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")

    cmd = [
        FFMPEG, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        "-movflags", "+faststart",
        FINAL_OUTPUT
    ]
    subprocess.run(cmd, check=True)

    # Copy to repo docs/demo/
    subprocess.run(["cp", FINAL_OUTPUT, REPO_OUTPUT], check=True)

    print(f"\n=======================================================")
    print(f"🎉 MASTER DEMO VIDEO GENERATED SUCCESSFULLY!")
    print(f"  Output 1: {FINAL_OUTPUT}")
    print(f"  Output 2: {REPO_OUTPUT}")
    print(f"=======================================================")

def main():
    start_time = time.time()
    clip_paths = []
    for idx, c in enumerate(CLIPS):
        p = render_clip(idx, c)
        clip_paths.append(p)
    outro_path = render_outro()
    clip_paths.append(outro_path)

    concat_clips(clip_paths)
    elapsed = time.time() - start_time
    print(f"Total processing time: {elapsed:.1f}s")

if __name__ == "__main__":
    main()
