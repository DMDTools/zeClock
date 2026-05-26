"""
Runtime installation and initialization module for zeClock.
Handles downloading and configuring dmdserver and DotClk resources.
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
import tempfile

GITHUB_REPO_DMD = "vpinball/libdmdutil"
GITHUB_REPO_RESOURCES = "sigmafx/DotClk-Resources"

ZECLOCK_DIR = Path.home() / ".zeclock"
INSTALL_DIR = ZECLOCK_DIR / "bin"
CONFIG_DIR = ZECLOCK_DIR / "config"
RESOURCES_DIR = ZECLOCK_DIR / "resources"

# ANSI Color handling
try:
    import colorama
    colorama.init()
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'
except ImportError:
    GREEN = YELLOW = RED = BLUE = NC = ''


def print_color(color, text):
    """Prints colored text to console"""
    print(f"{color}{text}{NC}")


# ==============================================================================
# DMDSERVER (libdmdutil) INSTALLATION LOGIC
# ==============================================================================

def detect_platform() -> str:
    """Detects system platform and architecture"""
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
        raise RuntimeError(f"Unsupported platform: {system} {machine}")


def get_latest_dmd_version() -> str:
    """Retrieves the latest version of libdmdutil from GitHub"""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO_DMD}/releases/latest"
    req = urllib.request.Request(api_url, headers={'User-Agent': 'zeClock-Installer'})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
        return data["tag_name"]


def download_dmd_release(platform_id: str, version: str, temp_dir: Path) -> Path:
    """Downloads corresponding libdmdutil release archive"""
    extension = "zip" if "win" in platform_id else "tar.gz"
    version_clean = version.lstrip('v')
    filename = f"libdmdutil-{version_clean}-{platform_id}.{extension}"
    url = f"https://github.com/{GITHUB_REPO_DMD}/releases/download/{version}/{filename}"
    
    print_color(BLUE, f"🌐 Platform: {platform_id}")
    print_color(YELLOW, f"📥 Downloading: {filename}")
    
    archive_path = temp_dir / filename
    
    # Simple progress hook
    def progress_hook(block_num, block_size, total_size):
        if total_size > 0:
            percent = min(100, block_num * block_size * 100 / total_size)
            sys.stdout.write(f"\r   Progress: {percent:.1f}%")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, archive_path, progress_hook)
    print()  # New line after progress
    print_color(GREEN, "✅ Download complete")
    
    print_color(YELLOW, "📂 Extracting archive...")
    if extension == "zip":
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
    else:
        with tarfile.open(archive_path, 'r:gz') as tar_ref:
            tar_ref.extractall(temp_dir)
    
    return temp_dir


def install_dmd_files(source_dir: Path):
    """Installs dmdserver files to destination directory"""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    print_color(BLUE, f"📦 Installing to: {INSTALL_DIR}")
    
    installed_count = 0
    # Copy all relevant files
    for pattern in ["dmdserver*", "*.so*", "*.dylib", "*.dll", "*.a"]:
        for file in source_dir.rglob(pattern):
            if file.is_file():
                dest = INSTALL_DIR / file.name
                shutil.copy2(file, dest)
                if file.suffix in ['', '.so', '.dylib'] or 'dmdserver' in file.name:
                    try:
                        dest.chmod(0o755)
                    except Exception:
                        pass  # Ignore chmod errors on unsupported OSes
                print(f"   ✓ {file.name}")
                installed_count += 1
                
    if installed_count == 0:
        raise FileNotFoundError("No dmdserver binary or libraries found in the downloaded archive.")


def create_default_config():
    """Generates default dmdserver config if missing"""
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
        print_color(GREEN, f"✅ Default configuration created: {config_file}")


def install_dmdserver() -> bool:
    """Main dmdserver installation driver"""
    print_color(GREEN, "╔════════════════════════════════════════════╗")
    print_color(GREEN, "║  🔧 Installing dmdserver (libdmdutil)      ║")
    print_color(GREEN, "╚════════════════════════════════════════════╝\n")
    
    temp_path = Path(tempfile.mkdtemp(prefix="libdmdutil-install-"))
    try:
        platform_id = detect_platform()
        
        print_color(YELLOW, "🔍 Fetching latest version from GitHub...")
        version = get_latest_dmd_version()
        print_color(GREEN, f"   Latest version found: {version}\n")
        
        download_dmd_release(platform_id, version, temp_path)
        install_dmd_files(temp_path)
        create_default_config()
        
        print_color(GREEN, "\n✅ dmdserver installation successful!")
        return True
    except Exception as e:
        print_color(RED, f"\n❌ dmdserver installation failed: {e}")
        return False
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


# ==============================================================================
# DOTCLK RESOURCES (Animations + Fonts) INSTALLATION LOGIC
# ==============================================================================

def download_resources_archive(temp_dir: Path) -> Path:
    """Downloads DotClk-Resources ZIP from GitHub"""
    print_color(BLUE, "📦 Downloading DotClk resources...")
    download_url = f"https://github.com/{GITHUB_REPO_RESOURCES}/archive/refs/heads/master.zip"
    archive_path = temp_dir / "dotclk-resources.zip"
    
    print_color(YELLOW, f"🌐 Downloading from: {download_url}")
    
    def progress_hook(block_num, block_size, total_size):
        if total_size > 0:
            percent = min(100, block_num * block_size * 100 / total_size)
            sys.stdout.write(f"\r   Progress: {percent:.1f}%")
            sys.stdout.flush()
            
    urllib.request.urlretrieve(download_url, archive_path, progress_hook)
    print()  # New line after progress
    print_color(GREEN, "✅ Resources download complete")
    
    print_color(YELLOW, "📂 Extracting archive...")
    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)
        
    extracted_dirs = list(temp_dir.glob("DotClk-Resources-*"))
    if not extracted_dirs:
        raise FileNotFoundError("Extracted directory not found in the ZIP archive.")
        
    return extracted_dirs[0]


def install_dotclk_files(source_dir: Path):
    """Installs fonts and animations into ~/.zeclock"""
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    print_color(BLUE, f"📦 Installing resources to: {RESOURCES_DIR}")
    
    # 1. Install fonts
    fonts_src = source_dir / "Fonts"
    fonts_dst = RESOURCES_DIR / "Fonts"
    if fonts_src.exists():
        if fonts_dst.exists():
            shutil.rmtree(fonts_dst)
        shutil.copytree(fonts_src, fonts_dst)
        font_count = len(list(fonts_dst.glob("*.fnt")))
        print_color(GREEN, f"   ✓ {font_count} bitmap fonts (.fnt) installed")
    else:
        print_color(YELLOW, "   ⚠️ Fonts directory missing from downloaded resources.")
        
    # 2. Install animations
    scenes_src = source_dir / "Scenes"
    scenes_dst = RESOURCES_DIR / "animations"
    if scenes_src.exists():
        if scenes_dst.exists():
            shutil.rmtree(scenes_dst)
        shutil.copytree(scenes_src, scenes_dst)
        scn_count = len(list(scenes_dst.rglob("*.scn")))
        print_color(GREEN, f"   ✓ {scn_count} retro animations (.scn) installed")
    else:
        print_color(YELLOW, "   ⚠️ Scenes directory missing from downloaded resources.")


def create_resources_readme():
    """Generates informative README.txt file inside resources folder"""
    readme_path = RESOURCES_DIR / "README.txt"
    readme_content = """DotClk Resources for zeClock
=============================

These resources are sourced from the original DotClk project:
https://github.com/sigmafx/DotClk-Resources

Contents:
- Fonts/      : Bitmap .fnt fonts
- animations/ : Retro .scn animations (2300+)
"""
    readme_path.write_text(readme_content.strip())
    print_color(GREEN, "   ✓ README.txt created")


def install_dotclk_resources() -> bool:
    """Main DotClk resources installation driver"""
    print_color(GREEN, "╔════════════════════════════════════════════╗")
    print_color(GREEN, "║  🎨 Installing DotClk Resources           ║")
    print_color(GREEN, "╚════════════════════════════════════════════╝\n")
    
    temp_path = Path(tempfile.mkdtemp(prefix="dotclk-resources-install-"))
    try:
        source_dir = download_resources_archive(temp_path)
        install_dotclk_files(source_dir)
        create_resources_readme()
        
        print_color(GREEN, "\n✅ Resources installation successful!")
        return True
    except Exception as e:
        print_color(RED, f"\n❌ Resources installation failed: {e}")
        return False
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


# ==============================================================================
# GLOBAL RUNTIME DIAGNOSTIC & BOOTSTRAPPER
# ==============================================================================

def is_dmdserver_installed() -> bool:
    """Checks if the dmdserver binary is present and executable"""
    executable_name = "dmdserver.exe" if platform.system() == "Windows" else "dmdserver"
    dmdserver_bin = INSTALL_DIR / executable_name
    return dmdserver_bin.exists() and os.access(dmdserver_bin, os.X_OK)


def are_resources_installed() -> bool:
    """Checks if fonts and animations directories contain files"""
    fonts_dir = RESOURCES_DIR / "Fonts"
    animations_dir = RESOURCES_DIR / "animations"
    
    has_fonts = fonts_dir.exists() and any(fonts_dir.glob("*.fnt"))
    has_animations = animations_dir.exists() and any(animations_dir.rglob("*.scn"))
    
    return has_fonts and has_animations


def check_and_install_resources(interactive: bool = True) -> bool:
    """
    Checks user's local installations.
    Downloads and configures missing parts interactively or automatically.
    """
    dmd_missing = not is_dmdserver_installed()
    resources_missing = not are_resources_installed()
    
    if not dmd_missing and not resources_missing:
        return True
        
    print_color(YELLOW, "📦 [zeClock Diagnostic] Required resources are missing:")
    if dmd_missing:
        print("  - The 'dmdserver' rendering server is not installed.")
    if resources_missing:
        print("  - The DotClk retro fonts and animations (2300+ files) are missing.")
    print()
    
    if interactive:
        try:
            choice = input("👉 Would you like to download and install them automatically now? [Y/n]: ").strip().lower()
            if choice not in ('', 'y', 'yes', 'o', 'oui'):
                print_color(RED, "\n🛑 Installation cancelled by user. zeClock will not be able to start properly.")
                return False
        except KeyboardInterrupt:
            print_color(RED, "\n🛑 Cancelled.")
            return False
            
    # Launch installation pipeline
    success = True
    if dmd_missing:
        success = success and install_dmdserver()
        print()
    if resources_missing:
        success = success and install_dotclk_resources()
        print()
        
    if success:
        print_color(GREEN, "🎉 zeClock initialization completed successfully!")
        print(f"  - Binaries:   {INSTALL_DIR}")
        print(f"  - Resources:  {RESOURCES_DIR}")
        print(f"  - Config:     {CONFIG_DIR}/dmdserver.ini\n")
    else:
        print_color(RED, "⚠️ Initialization encountered errors. Please check your internet connection and disk permissions.")
        
    return success
