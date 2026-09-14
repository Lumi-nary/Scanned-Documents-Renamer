"""Script to activate one of the candidate icon designs for Scanned Documents Renamer.

Usage:
    python scripts/set_app_icon.py 1   # Glassmorphic AI Scan Beam (Default)
    python scripts/set_app_icon.py 2   # Smart Auto-Filing Folder
    python scripts/set_app_icon.py 3   # Optical OCR & Rename Badge
    python scripts/set_app_icon.py 4   # Orbital Cyber Rings & Document
"""

import sys
import os
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ICONS_DIR = os.path.join(ROOT_DIR, "gui", "assets", "icons")
DEST_ICO = os.path.join(ROOT_DIR, "gui", "icon.ico")
DEST_PNG = os.path.join(ROOT_DIR, "gui", "icon.png")


def set_icon(choice: int) -> bool:
    src_ico = os.path.join(ICONS_DIR, f"concept_{choice}.ico")
    src_png = os.path.join(ICONS_DIR, f"concept_{choice}.png")

    if not os.path.exists(src_ico) or not os.path.exists(src_png):
        print(f"[ERROR] Icon concept #{choice} not found in {ICONS_DIR}")
        return False

    shutil.copyfile(src_ico, DEST_ICO)
    shutil.copyfile(src_png, DEST_PNG)
    print(f"[OK] Activated Concept #{choice} as active application icon.")
    print(f"     -> {DEST_ICO}")
    print(f"     -> {DEST_PNG}")
    return True


if __name__ == "__main__":
    selection = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    if not (1 <= selection <= 4):
        print("Please choose a number between 1 and 4.")
        sys.exit(1)
    set_icon(selection)
