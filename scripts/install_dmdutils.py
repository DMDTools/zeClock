#!/usr/bin/env python3
"""
Script d'installation de libdmdutil pour zeClock
Détecte automatiquement la plateforme et télécharge la bonne release
"""
import platform
import sys
import os
import urllib.request
import json
import tarfile
import zipfile
from pathlib import Path
import shutil

GITHUB_REPO = "vpinball/libdmdutil"
INSTALL_DIR = Path.home() / ".zeclock" / "bin"
CONFIG_DIR = Path.home() / ".zeclock" / "config"

def detect_platform():
    """Détecte la plateforme et l'architecture"""
    system = platform.system()
    machine = platform.machine()
    
    platform_map = {
        ("Linux", "x86_64"): "linux-x64",
        ("Linux", "aarch64"): "linux-aarch64",
        ("Linux", "arm64"): "linux-aarch64",
        ("Darwin", "arm64"): "macos-arm64",
        ("Darwin", "x86_64"): "macos-x64",
        ("Windows", "AMD64"): "win-x64",
    }
    
    key = (system, machine)
    if key in platform_map:
        return platform_map[key]
    else:
        print(f"❌ Unsupported platform: {system} {machine}")
        sys.exit(1)

def get_latest_version():
    """Récupère la dernière version depuis GitHub"""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    with urllib.request.urlopen(api_url) as response:
        data = json.loads(response.read())
        return data["tag_name"]

def download_release(platform_id, version):
    """Télécharge la release correspondante"""
    extension = "zip" if "win" in platform_id else "tar.gz"
    # Remove 'v' prefix from version for filename
    version_clean = version.lstrip('v')
    filename = f"libdmdutil-{version_clean}-{platform_id}.{extension}"
    url = f"https://github.com/{GITHUB_REPO}/releases/download/{version}/{filename}"
    
    print(f"🌐 Platform: {platform_id}")
    print(f"📥 Downloading: {filename}")
    
    temp_dir = Path("/tmp/libdmdutil-install")
    temp_dir.mkdir(exist_ok=True)
    archive_path = temp_dir / filename
    
    urllib.request.urlretrieve(url, archive_path)
    print("✅ Download complete")
    
    # Extraire
    print("📂 Extracting...")
    if extension == "zip":
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
    else:
        with tarfile.open(archive_path, 'r:gz') as tar_ref:
            tar_ref.extractall(temp_dir)
    
    return temp_dir

def install_files(source_dir):
    """Installe les fichiers dans le dossier de destination"""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"📦 Installing to: {INSTALL_DIR}")
    
    # Copier tous les fichiers pertinents
    for pattern in ["dmdserver*", "*.so*", "*.dylib", "*.dll", "*.a"]:
        for file in source_dir.rglob(pattern):
            if file.is_file():
                dest = INSTALL_DIR / file.name
                shutil.copy2(file, dest)
                if file.suffix in ['', '.so', '.dylib']:
                    dest.chmod(0o755)
                print(f"   ✓ {file.name}")

def create_config():
    """Crée la configuration par défaut"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_file = CONFIG_DIR / "dmdserver.ini"
    
    if not config_file.exists():
        config_file.write_text("""[DMDServer]
Addr = 0.0.0.0
Port = 6789

[ZeDMD]
Enabled = 1
Brightness = 10
""")
        print(f"✅ Config created: {config_file}")

def main():
    print("📦 Installing libdmdutil for zeClock\n")
    
    # Détecter la plateforme
    platform_id = detect_platform()
    
    # Récupérer la version
    print("🔍 Fetching latest version...")
    version = get_latest_version()
    print(f"   Latest: {version}\n")
    
    # Télécharger
    temp_dir = download_release(platform_id, version)
    
    # Installer
    install_files(temp_dir)
    
    # Config
    create_config()
    
    # Nettoyer
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    print("\n✅ Installation complete!")
    print(f"\n🚀 Start dmdserver:")
    print(f"   {INSTALL_DIR}/dmdserver -a 0.0.0.0 -p 6789 -w -l")

if __name__ == "__main__":
    main()
