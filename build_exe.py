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

    # Clean old build/dist app directory
    build_dir = os.path.join(base_dir, "build")
    if os.path.exists(build_dir):
        print("Cleaning previous build/ directory...")
        try:
            shutil.rmtree(build_dir)
        except Exception as e:
            print(f"Notice: Could not completely remove {build_dir}: {e}")

    app_dist_dir = os.path.join(base_dir, "dist", "ScannedDocumentsRenamer")
    if os.path.exists(app_dist_dir):
        print("Cleaning previous dist/ScannedDocumentsRenamer directory...")
        try:
            shutil.rmtree(app_dist_dir)
        except Exception as e:
            print(f"Notice: Could not completely remove {app_dist_dir}: {e}")

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

    # Copy template config & instructions to distribution root for portable operation
    src_instructions = os.path.join(base_dir, "instructions.json")
    if os.path.exists(src_instructions):
        shutil.copyfile(src_instructions, os.path.join(dist_dir, "instructions.json"))

    src_settings_example = os.path.join(base_dir, "settings.example.json")
    if os.path.exists(src_settings_example):
        shutil.copyfile(src_settings_example, os.path.join(dist_dir, "settings.example.json"))

    # Ensure local settings or secrets are NEVER packaged in clean distribution
    dist_settings = os.path.join(dist_dir, "settings.json")
    if os.path.exists(dist_settings):
        os.remove(dist_settings)

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
