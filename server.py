"""Convenience launcher:  python server.py   (same as: python -m repobrain serve --demo)"""
import sys

from repobrain.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["serve", "--demo"] + sys.argv[1:]))
