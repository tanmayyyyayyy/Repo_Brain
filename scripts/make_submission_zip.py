#!/usr/bin/env python3
"""
Generates the official clean submission ZIP archive for Unstop Round 3 Finals.
Excludes git history, virtualenvs, __pycache__, and temporary files.
Computes SHA-256 checksum of the archive.
"""
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.expanduser("~/Downloads")
ZIP_NAME = "RepoBrain_Round3_Final_Submission.zip"
OUT_PATH = os.path.join(OUT_DIR, ZIP_NAME)

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".DS_Store",
    "test_runs",
    "before",
}

EXCLUDE_EXTS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".DS_Store",
    ".log",
    ".tmp",
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
    ".avi",
}

EXCLUDE_FILES = {
    ".DS_Store",
    "raw_screen_recording.mov",
}


def should_exclude(rel_path):
    parts = rel_path.split(os.sep)
    for p in parts:
        if p in EXCLUDE_DIRS:
            return True
    base = os.path.basename(rel_path)
    if base in EXCLUDE_FILES:
        return True
    _, ext = os.path.splitext(base)
    if ext in EXCLUDE_EXTS:
        return True
    return False


def main():
    print(f"📦 Packaging RepoBrain submission from: {ROOT}")
    print(f"🎯 Output target: {OUT_PATH}")

    total_files = 0
    total_bytes = 0

    with zipfile.ZipFile(OUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            # Prune excluded directories in-place
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

            for fname in sorted(filenames):
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, ROOT)

                if should_exclude(rel_path):
                    continue

                # Don't include raw 60MB+ screen captures in zip (keep edited demo)
                if "raw_screen_recording" in fname or fname.endswith(".mov"):
                    continue

                arcname = os.path.join("repobrain-prototype", rel_path)
                zf.write(full_path, arcname)
                total_files += 1
                total_bytes += os.path.getsize(full_path)

    zip_size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)

    # Compute SHA-256
    hasher = hashlib.sha256()
    with open(OUT_PATH, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    sha256 = hasher.hexdigest()

    print("\n" + "=" * 60)
    print("✅ SUBMISSION ZIP CREATED SUCCESSFULLY!")
    print(f"📁 Path: {OUT_PATH}")
    print(f"📊 Files packaged: {total_files}")
    print(f"💾 Uncompressed size: {total_bytes / (1024*1024):.2f} MB")
    print(f"📦 Archive size: {zip_size_mb:.2f} MB")
    print(f"🔑 SHA-256: {sha256}")
    print("=" * 60)


if __name__ == "__main__":
    main()

