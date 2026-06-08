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
GITHUB_REPO_ZEDMD = "PPUC/libzedmd"
GITHUB_REPO_RESOURCES = "sigmafx/DotClk-Resources"

from .paths import get_data_dir, get_config_dir, get_install_dir, get_lib_dir, get_resources_dir

ZECLOCK_DIR = get_data_dir()
INSTALL_DIR = get_install_dir()
LIB_DIR = get_lib_dir()
CONFIG_DIR = get_config_dir()
RESOURCES_DIR = get_resources_dir()

# ANSI Color handling
try:
    import colorama

    colorama.init()
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[0;31m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"
except ImportError:
    GREEN = YELLOW = RED = BLUE = NC = ""


def print_color(color: str, text: str) -> None:
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
    req = urllib.request.Request(api_url, headers={"User-Agent": "zeClock-Installer"})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
        return data["tag_name"]


def download_dmd_release(platform_id: str, version: str, temp_dir: Path) -> Path:
    """Downloads corresponding libdmdutil release archive"""
    extension = "zip" if "win" in platform_id else "tar.gz"
    version_clean = version.lstrip("v")
    filename = f"libdmdutil-{version_clean}-{platform_id}.{extension}"
    url = f"https://github.com/{GITHUB_REPO_DMD}/releases/download/{version}/{filename}"

    print_color(BLUE, f"🌐 Platform: {platform_id}")
    print_color(YELLOW, f"📥 Downloading: {filename}")

    archive_path = temp_dir / filename

    # Simple progress hook
    def progress_hook(block_num: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            percent = min(100, block_num * block_size * 100 / total_size)
            sys.stdout.write(f"\r   Progress: {percent:.1f}%")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, archive_path, progress_hook)
    print()  # New line after progress
    print_color(GREEN, "✅ Download complete")

    print_color(YELLOW, "📂 Extracting archive...")
    if extension == "zip":
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)
    else:
        with tarfile.open(archive_path, "r:gz") as tar_ref:
            tar_ref.extractall(temp_dir)

    return temp_dir


def install_dmd_files(source_dir: Path) -> None:
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
                if file.suffix in ["", ".so", ".dylib"] or "dmdserver" in file.name:
                    try:
                        dest.chmod(0o755)
                    except Exception:
                        pass  # Ignore chmod errors on unsupported OSes
                print(f"   ✓ {file.name}")
                installed_count += 1

    if installed_count == 0:
        raise FileNotFoundError(
            "No dmdserver binary or libraries found in the downloaded archive."
        )


def create_default_config() -> None:
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
# LIBZEDMD INSTALLATION LOGIC
# ==============================================================================

LIBZEDMD_VERSION_FILE = LIB_DIR / ".libzedmd-version"

# Platform-specific library filenames for libzedmd
LIBZEDMD_LIBS = {
    "Linux": ["libzedmd.so", "libsockpp.so", "libserialport.so"],
    "Darwin": ["libzedmd.dylib", "libsockpp.dylib", "libserialport.dylib"],
    "Windows": ["zedmd.dll", "sockpp.dll", "serialport.dll"],
}


def get_latest_zedmd_version() -> str:
    """Retrieves the latest version of libzedmd from GitHub"""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO_ZEDMD}/releases/latest"
    req = urllib.request.Request(api_url, headers={"User-Agent": "zeClock-Installer"})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
        return data["tag_name"]


def is_libzedmd_installed() -> bool:
    """Checks if libzedmd is installed and version file exists"""
    system = platform.system()
    libs = LIBZEDMD_LIBS.get(system, [])
    if not libs:
        return False

    # Check that at least the main library exists
    main_lib = LIB_DIR / libs[0]
    if not main_lib.exists():
        return False

    # Check version file exists
    if not LIBZEDMD_VERSION_FILE.exists():
        return False

    return True


def install_libzedmd() -> bool:
    """Main libzedmd installation driver"""
    print_color(GREEN, "╔════════════════════════════════════════════╗")
    print_color(GREEN, "║  🔧 Installing libzedmd                    ║")
    print_color(GREEN, "╚════════════════════════════════════════════╝\n")

    temp_path = Path(tempfile.mkdtemp(prefix="libzedmd-install-"))
    try:
        platform_id = detect_platform()

        print_color(YELLOW, "🔍 Fetching latest version from GitHub...")
        version = get_latest_zedmd_version()
        print_color(GREEN, f"   Latest version found: {version}\n")

        # Check if already installed with same version
        if is_libzedmd_installed() and LIBZEDMD_VERSION_FILE.exists():
            installed_version = LIBZEDMD_VERSION_FILE.read_text().strip()
            if installed_version == version:
                print_color(
                    GREEN,
                    f"✅ libzedmd {version} is already installed. Skipping download.",
                )
                return True

        # Download and install
        _download_libzedmd_release(platform_id, version, temp_path)
        _install_libzedmd_files(temp_path)

        # Write version file
        LIBZEDMD_VERSION_FILE.write_text(version)

        print_color(GREEN, "\n✅ libzedmd installation successful!")
        return True
    except Exception as e:
        print_color(RED, f"\n❌ libzedmd installation failed: {e}")
        print_color(
            YELLOW,
            f"   You can download manually from: https://github.com/{GITHUB_REPO_ZEDMD}/releases",
        )
        return False
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


def _get_release_filename(platform_id: str, version_clean: str) -> str:
    """Map our platform_id to the actual GitHub release asset filename.

    The PPUC/libzedmd releases use these naming conventions:
    - macOS: libzedmd-{version}-macos.tar.gz (universal, no arch suffix)
    - Windows x64: libzedmd-{version}-win-x64.zip
    - Windows x86: libzedmd-{version}-win-x86.zip
    - Linux: NOT available as pre-built — must build from source
    """
    mapping = {
        "macos-arm64": f"libzedmd-{version_clean}-macos.tar.gz",
        "macos-x64": f"libzedmd-{version_clean}-macos.tar.gz",
        "win-x64": f"libzedmd-{version_clean}-win-x64.zip",
    }
    filename = mapping.get(platform_id)
    if not filename:
        raise RuntimeError(
            f"No pre-built libzedmd binary available for platform '{platform_id}'. "
            f"Linux requires building from source."
        )
    return filename


def _download_libzedmd_release(platform_id: str, version: str, temp_dir: Path) -> Path:
    """Downloads corresponding libzedmd release archive.

    For Linux platforms, builds from source instead of downloading a pre-built binary.
    """
    # Linux has no pre-built binaries — build from source
    if "linux" in platform_id:
        return _build_libzedmd_from_source(platform_id, version, temp_dir)

    version_clean = version.lstrip("v")
    filename = _get_release_filename(platform_id, version_clean)
    extension = "zip" if filename.endswith(".zip") else "tar.gz"
    url = (
        f"https://github.com/{GITHUB_REPO_ZEDMD}/releases/download/{version}/{filename}"
    )

    print_color(BLUE, f"🌐 Platform: {platform_id}")
    print_color(YELLOW, f"📥 Downloading: {filename}")

    archive_path = temp_dir / filename

    def progress_hook(block_num: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            percent = min(100, block_num * block_size * 100 / total_size)
            sys.stdout.write(f"\r   Progress: {percent:.1f}%")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, archive_path, progress_hook)
    print()  # New line after progress
    print_color(GREEN, "✅ Download complete")

    print_color(YELLOW, "📂 Extracting archive...")
    if extension == "zip":
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)
    else:
        with tarfile.open(archive_path, "r:gz") as tar_ref:
            tar_ref.extractall(temp_dir)

    return temp_dir


def _build_libzedmd_from_source(platform_id: str, version: str, temp_dir: Path) -> Path:
    """Build libzedmd from source for Linux (no pre-built binaries available).

    Tries Docker-based build first (no host dependencies needed beyond Docker).
    Falls back to native build if Docker is unavailable.
    Requires either:
      - Docker with BuildKit support, OR
      - git, cmake, gcc/g++, make, libtool, automake, autoconf
    """
    print_color(BLUE, f"🌐 Platform: {platform_id} (building from source)")

    # Determine arch from platform_id
    arch = "x64" if "x64" in platform_id else "aarch64"

    # Try Docker-based build first (handles all dependencies)
    if _try_docker_build(version, temp_dir):
        return temp_dir

    # Fall back to native build
    print_color(YELLOW, "🐳 Docker not available, trying native build...")
    return _native_build_libzedmd(platform_id, arch, version, temp_dir)


def _try_docker_build(version: str, temp_dir: Path) -> bool:
    """Attempt to build libzedmd using Docker. Returns True on success."""
    import subprocess

    # Check if docker is available
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

    print_color(
        YELLOW, "🐳 Building libzedmd via Docker (this may take a few minutes)..."
    )

    # Find the Dockerfile
    # Look relative to this file's location
    script_dir = Path(__file__).parent.parent / "scripts"
    dockerfile = script_dir / "build-libzedmd.Dockerfile"

    if not dockerfile.exists():
        # Try relative to CWD
        dockerfile = Path("scripts/build-libzedmd.Dockerfile")
        if not dockerfile.exists():
            print_color(
                YELLOW,
                "   ⚠️  build-libzedmd.Dockerfile not found, skipping Docker build",
            )
            return False

    try:
        subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(dockerfile),
                "--output",
                f"type=local,dest={temp_dir}",
                str(dockerfile.parent.parent),
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "DOCKER_BUILDKIT": "1"},
        )
        print_color(GREEN, "✅ Docker build complete")
        return True
    except subprocess.CalledProcessError as e:
        print_color(
            YELLOW,
            f"   ⚠️  Docker build failed: {e.stderr[-200:] if e.stderr else 'unknown error'}",
        )
        return False


def _native_build_libzedmd(
    platform_id: str, arch: str, version: str, temp_dir: Path
) -> Path:
    """Build libzedmd natively. Requires git, cmake, gcc, make, libtool, automake, autoconf."""
    import subprocess

    print_color(YELLOW, f"📥 Cloning libzedmd {version}...")

    # Clone the repo at the specific version tag
    repo_dir = temp_dir / "libzedmd"
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                version,
                f"https://github.com/{GITHUB_REPO_ZEDMD}.git",
                str(repo_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to clone libzedmd: {e.stderr}") from e

    print_color(GREEN, "✅ Clone complete")

    # Run external dependencies script
    external_script = repo_dir / "platforms" / "linux" / arch / "external.sh"
    if external_script.exists():
        print_color(YELLOW, f"🔧 Building external dependencies ({arch})...")
        print_color(YELLOW, "   (requires: libtool, automake, autoconf, pkg-config)")
        try:
            subprocess.run(
                ["bash", str(external_script)],
                check=True,
                capture_output=True,
                text=True,
                cwd=str(repo_dir),
            )
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr[-500:] if e.stderr else "unknown error"
            if "libtool" in error_msg.lower() or "LIBTOOL" in error_msg:
                raise RuntimeError(
                    "Build failed: missing 'libtool'. Install it with:\n"
                    "  sudo apt install libtool automake autoconf pkg-config\n"
                    "Or use the Docker-based builder:\n"
                    "  scripts/build-libzedmd.sh"
                ) from e
            raise RuntimeError(
                f"Failed to build external dependencies: {error_msg}"
            ) from e
        print_color(GREEN, "✅ External dependencies built")
    else:
        print_color(
            YELLOW, f"⚠️  No external script found at {external_script}, skipping"
        )

    # Build with cmake
    build_dir = repo_dir / "build"
    print_color(YELLOW, "🔧 Building libzedmd with cmake...")
    try:
        subprocess.run(
            [
                "cmake",
                "-DPLATFORM=linux",
                f"-DARCH={arch}",
                "-DCMAKE_BUILD_TYPE=Release",
                "-B",
                str(build_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(repo_dir),
        )
        subprocess.run(
            ["cmake", "--build", str(build_dir), "--", f"-j{os.cpu_count() or 2}"],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(repo_dir),
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to build libzedmd: {e.stderr[-500:]}") from e

    print_color(GREEN, "✅ Build complete")

    # The built libraries should be in build/ or build/Release/
    # Copy them to temp_dir so _install_libzedmd_files can find them
    for pattern in ["*.so*", "*.so"]:
        for lib_file in build_dir.rglob(pattern):
            if lib_file.is_file():
                shutil.copy2(lib_file, temp_dir / lib_file.name)

    # Also check third-party/runtime libs that were built by external.sh
    runtime_libs = repo_dir / "third-party" / "runtime-libs" / "linux" / arch
    if runtime_libs.exists():
        for lib_file in runtime_libs.glob("*.so*"):
            if lib_file.is_file():
                shutil.copy2(lib_file, temp_dir / lib_file.name)

    return temp_dir


def _install_libzedmd_files(source_dir: Path) -> None:
    """Installs libzedmd library files to ~/.zeclock/lib/"""
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    print_color(BLUE, f"📦 Installing to: {LIB_DIR}")

    system = platform.system()
    expected_libs = LIBZEDMD_LIBS.get(system, [])

    installed_count = 0
    # Find and copy library files matching the expected patterns
    for lib_name in expected_libs:
        # Search for the library (including versioned variants like .so.1.2.3)
        for file in source_dir.rglob(f"{lib_name}*"):
            if file.is_file():
                dest = LIB_DIR / file.name
                shutil.copy2(file, dest)
                try:
                    dest.chmod(0o755)
                except Exception:
                    pass  # Ignore chmod errors on unsupported OSes
                print(f"   ✓ {file.name}")
                installed_count += 1

    if installed_count == 0:
        raise FileNotFoundError(
            "No libzedmd libraries found in the downloaded archive."
        )


# ==============================================================================
# DOTCLK RESOURCES (Animations + Fonts) INSTALLATION LOGIC
# ==============================================================================


def download_resources_archive(temp_dir: Path) -> Path:
    """Downloads DotClk-Resources ZIP from GitHub"""
    print_color(BLUE, "📦 Downloading DotClk resources...")
    download_url = (
        f"https://github.com/{GITHUB_REPO_RESOURCES}/archive/refs/heads/master.zip"
    )
    archive_path = temp_dir / "dotclk-resources.zip"

    print_color(YELLOW, f"🌐 Downloading from: {download_url}")

    def progress_hook(block_num: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            percent = min(100, block_num * block_size * 100 / total_size)
            sys.stdout.write(f"\r   Progress: {percent:.1f}%")
            sys.stdout.flush()

    urllib.request.urlretrieve(download_url, archive_path, progress_hook)
    print()  # New line after progress
    print_color(GREEN, "✅ Resources download complete")

    print_color(YELLOW, "📂 Extracting archive...")
    with zipfile.ZipFile(archive_path, "r") as zip_ref:
        zip_ref.extractall(temp_dir)

    extracted_dirs = list(temp_dir.glob("DotClk-Resources-*"))
    if not extracted_dirs:
        raise FileNotFoundError("Extracted directory not found in the ZIP archive.")

    return extracted_dirs[0]


def install_dotclk_files(source_dir: Path) -> None:
    """Installs fonts and animations into ~/.zeclock"""
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    print_color(BLUE, f"📦 Installing resources to: {RESOURCES_DIR}")

    # Fonts are bundled in the package (zeclock/resources/Fonts/) — no download needed.

    # Install animations
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


def create_resources_readme() -> None:
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
    """Checks if animations are installed (fonts are bundled in the package)."""
    animations_dir = RESOURCES_DIR / "animations"
    has_animations = animations_dir.exists() and any(animations_dir.rglob("*.scn"))
    return has_animations


def check_and_install_resources(
    interactive: bool = True, backend: str = "auto"
) -> bool:
    """
    Checks user's local installations.
    Downloads and configures missing parts interactively or automatically.

    Args:
        interactive: Whether to prompt the user before installing.
        backend: The selected backend mode. When "dmdserver", libzedmd is not required.
    """
    # libzedmd is only needed for "auto" or "zedmd" backends
    need_libzedmd = backend in ("auto", "zedmd")
    libzedmd_missing = need_libzedmd and not is_libzedmd_installed()
    resources_missing = not are_resources_installed()

    if not libzedmd_missing and not resources_missing:
        return True

    print_color(YELLOW, "📦 [zeClock Diagnostic] Required resources are missing:")
    if libzedmd_missing:
        print("  - The 'libzedmd' library is not installed.")
    if resources_missing:
        print("  - The DotClk retro animations (2300+ .scn files) are missing.")
    print()

    if interactive:
        try:
            choice = (
                input(
                    "👉 Would you like to download and install them automatically now? [Y/n]: "
                )
                .strip()
                .lower()
            )
            if choice not in ("", "y", "yes", "o", "oui"):
                print_color(
                    RED,
                    "\n🛑 Installation cancelled by user. zeClock will not be able to start properly.",
                )
                return False
        except KeyboardInterrupt:
            print_color(RED, "\n🛑 Cancelled.")
            return False

    # Launch installation pipeline
    success = True
    if libzedmd_missing:
        success = success and install_libzedmd()
        print()
    if resources_missing:
        success = success and install_dotclk_resources()
        print()

    if success:
        print_color(GREEN, "🎉 zeClock initialization completed successfully!")
        print(f"  - Libraries:  {LIB_DIR}")
        print(f"  - Resources:  {RESOURCES_DIR}")
        print(f"  - Config:     {CONFIG_DIR}/zeclock.ini\n")
    else:
        print_color(
            RED,
            "⚠️ Initialization encountered errors. Please check your internet connection and disk permissions.",
        )

    return success
