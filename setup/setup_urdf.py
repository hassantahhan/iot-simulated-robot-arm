"""Download the SO-ARM101 URDF and mesh assets from TheRobotStudio GitHub.

Run this once to fetch the model files:
    python device/setup_urdf.py

After running, the URDF and STL meshes will be in device/urdf/so101/
"""

import os
import urllib.request
import json

GITHUB_API_BASE = "https://api.github.com/repos/TheRobotStudio/SO-ARM100/contents/Simulation/SO101"
RAW_BASE = "https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100/main/Simulation/SO101"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "device", "urdf", "so101")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets")


def download_file(url: str, dest: str):
    """Download a file from URL to destination path."""
    print(f"  Downloading: {os.path.basename(dest)}")
    urllib.request.urlretrieve(url, dest)


def main():
    # Create directories
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # Download URDF file
    urdf_url = f"{RAW_BASE}/so101_new_calib.urdf"
    urdf_dest = os.path.join(OUTPUT_DIR, "so101.urdf")
    print("[1/3] Downloading SO-ARM101 URDF...")
    download_file(urdf_url, urdf_dest)

    # Download joint properties (may be referenced)
    props_url = f"{RAW_BASE}/joints_properties.xml"
    props_dest = os.path.join(OUTPUT_DIR, "joints_properties.xml")
    print("[2/3] Downloading joint properties...")
    download_file(props_url, props_dest)

    # Download all STL mesh files from assets/
    print("[3/3] Downloading mesh assets (STL files)...")
    api_url = f"{GITHUB_API_BASE}/assets"
    req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github.v3+json"})
    with urllib.request.urlopen(req) as response:
        items = json.loads(response.read().decode())

    stl_files = [item for item in items if item["name"].endswith(".stl")]
    print(f"  Found {len(stl_files)} STL mesh files")

    for item in stl_files:
        file_url = f"{RAW_BASE}/assets/{item['name']}"
        file_dest = os.path.join(ASSETS_DIR, item["name"])
        download_file(file_url, file_dest)

    print(f"\n[DONE] SO-ARM101 model saved to: {OUTPUT_DIR}")
    print(f"  URDF: {urdf_dest}")
    print(f"  Meshes: {ASSETS_DIR} ({len(stl_files)} files)")


if __name__ == "__main__":
    main()
