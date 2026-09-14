import os
import sys
import subprocess
import shutil

def get_folder_size(folder_path):
    total = 0
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            fp = os.path.join(root, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def build():
    print("=" * 65)
    print("  Building Scanned Documents Renamer Standalone Desktop App")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    spec_file = os.path.join(base_dir, "ScannedDocumentsRenamer.spec")

    if not os.path.exists(spec_file):
        print(f"[ERROR] Specification file not found at: {spec_file}")
        sys.exit(1)

    # Clean old build/dist
    for d in ["build", "dist"]:
        path = os.path.join(base_dir, d)
        if os.path.exists(path):
            print(f"Cleaning previous {d}/ directory...")
            try:
                shutil.rmtree(path)
            except Exception as e:
                print(f"Notice: Could not completely remove {path}: {e}")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "-y",
        spec_file
    ]

    print(f"Running PyInstaller command: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=base_dir)

    if proc.returncode != 0:
        print("[ERROR] PyInstaller compilation failed!")
        sys.exit(proc.returncode)

    dist_dir = os.path.join(base_dir, "dist", "ScannedDocumentsRenamer")
    exe_file = os.path.join(dist_dir, "ScannedDocumentsRenamer.exe")
    gui_file = os.path.join(dist_dir, "_internal", "gui", "index.html")
    if not os.path.exists(gui_file):
        gui_file = os.path.join(dist_dir, "gui", "index.html")

    if not os.path.exists(exe_file):
        print(f"[ERROR] Expected executable not found at: {exe_file}")
        sys.exit(1)

    if not os.path.exists(gui_file):
        print(f"[ERROR] Expected GUI asset not found at: {gui_file}")
        sys.exit(1)

    # Place standalone icon assets directly in distribution root for shortcuts & portable mode
    src_ico = os.path.join(base_dir, "gui", "icon.ico")
    src_png = os.path.join(base_dir, "gui", "icon.png")
    if os.path.exists(src_ico):
        shutil.copyfile(src_ico, os.path.join(dist_dir, "icon.ico"))
        shutil.copyfile(src_ico, os.path.join(dist_dir, "app.ico"))
    if os.path.exists(src_png):
        shutil.copyfile(src_png, os.path.join(dist_dir, "icon.png"))

    total_size = get_folder_size(dist_dir)

    print("\n" + "=" * 65)
    print("  BUILD SUCCESSFUL!")
    print("=" * 65)
    print(f"Output directory: {dist_dir}")
    print(f"Executable file:  {exe_file}")
    print(f"Total bundle size: {format_bytes(total_size)}")
    print("=" * 65)
    print("\nNon-technical users can run this application without Python installed!")
    print("To launch, simply run:\n  " + exe_file)

if __name__ == "__main__":
    build()
