import os
import sys
import subprocess
import requests

REPO = "Lumi-nary/Scanned-Documents-Renamer"
TAG = "v2.0.0"
RELEASE_NAME = "Scanned Documents Renamer v2.0.0"
ASSET_NAME = "ScannedDocumentsRenamer_Setup_v2.0.0.exe"

def get_github_token():
    # Try environment variable first
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    # Try git credential helper
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n",
            text=True,
            capture_output=True,
            check=True
        )
        for line in proc.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"Failed to fetch credentials from git helper: {e}")
    return None

RELEASE_BODY = """## 📁 Scanned Documents Renamer v2.0.0

Point it at your scanner's output folder. It reads every new scan, figures out what document it is, renames it properly, and files it neatly under the right client.

### 🌟 What's New in v2.0.0

- 📋 **Customizable Instructions Tab**:
  - Customize classification and renaming instructions for individual document types directly from the UI without writing code.
  - 10 pre-configured office presets (Corporate Certificates, Statements of Account / OPE, Tax Returns, BIR forms, Contracts, Invoices, IDs, etc.).
  - Add custom document types with keyword matching and custom naming patterns.
  - Live search and filter bar across all rules.
  - Real-time Multimodal AI Prompt Previewer with one-click clipboard copying.
  - Offline native rule matching engine for custom types.

- 💾 **Floating "Save Settings" Action Bar**:
  - Dirty-tracking popup bar with an animated unsaved changes badge in the bottom-right corner.
  - Quick "Discard" and "Save Settings" actions with unsaved change warnings when navigating tabs.

- 🔒 **100% Offline Local PP-OCR Engine**:
  - Local RapidOCR (ONNX) fallback for reading physical scans without digital text layers.
  - Zero external network requests, zero API fees, and complete client data privacy.

- 👤 **Smart Active Client Context**:
  - Lock scanning to a specific client for batch processing, or let AI auto-detect clients per document.

- 🖥️ **Windows Setup Installer**:
  - Modern Windows setup wizard (`ScannedDocumentsRenamer_Setup_v2.0.0.exe`).
  - Installs cleanly per-user without requiring administrator UAC elevation.
  - Creates Desktop & Start Menu shortcuts with full uninstaller support.

- 🧪 **Rock-Solid Reliability**:
  - 73/73 automated unit tests passing across all daemon, GUI bridge, OCR, worker, and instruction subsystems.

---

### ⬇️ Download
Download and run the installer below:
- **[ScannedDocumentsRenamer_Setup_v2.0.0.exe](https://github.com/Lumi-nary/Scanned-Documents-Renamer/releases/download/v2.0.0/ScannedDocumentsRenamer_Setup_v2.0.0.exe)** (98.23 MB)
"""

def main():
    token = get_github_token()
    if not token:
        print("[ERROR] Could not find GitHub token!")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Release-Publisher/2.0.0"
    }

    print(f"Publishing release '{TAG}' for {REPO}...")

    # Check if release exists
    rel_url = f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}"
    resp = requests.get(rel_url, headers=headers)
    
    if resp.status_code == 200:
        release = resp.json()
        print(f"Found existing release: ID {release['id']}")
    elif resp.status_code == 404:
        print("Release does not exist yet, creating release...")
        create_url = f"https://api.github.com/repos/{REPO}/releases"
        payload = {
            "tag_name": TAG,
            "target_commitish": "main",
            "name": RELEASE_NAME,
            "body": RELEASE_BODY,
            "draft": False,
            "prerelease": False
        }
        create_resp = requests.post(create_url, headers=headers, json=payload)
        if create_resp.status_code not in (200, 201):
            print(f"[ERROR] Failed to create release: {create_resp.status_code} {create_resp.text}")
            sys.exit(1)
        release = create_resp.json()
        print(f"Release created successfully! ID {release['id']}")
    else:
        print(f"[ERROR] Unexpected response checking release: {resp.status_code} {resp.text}")
        sys.exit(1)

    release_id = release["id"]

    # Locate installer asset
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    installer_path = os.path.join(base_dir, "dist", "installer", ASSET_NAME)
    if not os.path.exists(installer_path):
        installer_path = os.path.join(base_dir, "dist", ASSET_NAME)
    
    if not os.path.exists(installer_path):
        print(f"[ERROR] Installer file not found at: {installer_path}")
        sys.exit(1)

    file_size = os.path.getsize(installer_path)
    print(f"Installer binary found: {installer_path} ({file_size / (1024*1024):.2f} MB)")

    # Check existing assets and remove old duplicate if present
    for asset in release.get("assets", []):
        if asset["name"] == ASSET_NAME:
            print(f"Asset '{ASSET_NAME}' already exists (ID {asset['id']}), removing old asset first...")
            del_url = f"https://api.github.com/repos/{REPO}/releases/assets/{asset['id']}"
            del_resp = requests.delete(del_url, headers=headers)
            if del_resp.status_code == 204:
                print("Old asset deleted.")
            else:
                print(f"Warning: could not delete old asset: {del_resp.status_code}")

    # Upload new asset
    upload_url = f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets?name={ASSET_NAME}"
    upload_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size),
        "User-Agent": "Release-Publisher/2.0.0"
    }

    print(f"Uploading {ASSET_NAME} to GitHub release...")
    with open(installer_path, "rb") as f:
        upload_resp = requests.post(upload_url, headers=upload_headers, data=f)

    if upload_resp.status_code in (200, 201):
        asset_info = upload_resp.json()
        print("\n" + "=" * 65)
        print("  RELEASE PUBLISHED & ASSET UPLOADED SUCCESSFULLY!")
        print("=" * 65)
        print(f"Release URL: {release.get('html_url')}")
        print(f"Direct Download URL: {asset_info.get('browser_download_url')}")
        print("=" * 65)
    else:
        print(f"[ERROR] Asset upload failed: {upload_resp.status_code} {upload_resp.text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
