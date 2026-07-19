"""
Automatic OTA updater for zeClock via GitHub Releases.

Checks the latest release from DMDTools/zeClock on GitHub, compares with
the currently installed version, and performs an in-place update if a newer
version is available.

Designed to run unattended on a headless Raspberry Pi with a read-only
overlay filesystem and persistent /data partition.

Usage:
    python -m zeclock.updater          # Check and update if needed
    python -m zeclock.updater --check  # Only check, don't install
    python -m zeclock.updater --force  # Force reinstall even if up-to-date
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import __version__
from .paths import get_data_dir

logger = logging.getLogger(__name__)

GITHUB_REPO = "DMDTools/zeClock"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = "zeClock-OTA-Updater"

# Paths on the Raspberry Pi
APP_DIR = Path("/home/zeclock/app")
VENV_DIR = Path("/home/zeclock/venv")
OVERLAY_LOWER = Path("/overlay/lower")

# Update state is stored on the persistent /data partition
UPDATE_STATE_DIR = get_data_dir() / "update"
UPDATE_LOG_FILE = UPDATE_STATE_DIR / "update.log"
UPDATE_VERSION_FILE = UPDATE_STATE_DIR / "current-version"
UPDATE_LOCK_FILE = UPDATE_STATE_DIR / ".update-lock"


class UpdateError(Exception):
    """Raised when an update operation fails."""

    pass


class UpdateResult:
    """Result of an update check/install operation."""

    def __init__(
        self,
        updated: bool,
        current_version: str,
        latest_version: str,
        message: str,
    ):
        self.updated = updated
        self.current_version = current_version
        self.latest_version = latest_version
        self.message = message

    def __str__(self) -> str:
        return self.message


def _setup_logging() -> None:
    """Configure logging for standalone execution."""
    UPDATE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(UPDATE_LOG_FILE, mode="a"),
        ],
    )


def _get_installed_version() -> str:
    """Get the currently installed version.

    Checks the version file on /data first (tracks OTA updates),
    falls back to the package __version__.
    """
    if UPDATE_VERSION_FILE.exists():
        return UPDATE_VERSION_FILE.read_text().strip()
    return __version__


def _save_installed_version(version: str) -> None:
    """Persist the installed version to /data."""
    UPDATE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    UPDATE_VERSION_FILE.write_text(version + "\n")


def get_latest_release() -> dict:
    """Fetch the latest release information from GitHub API.

    Returns:
        Dictionary with keys: tag_name, zipball_url, published_at, body, assets
    """
    logger.info(f"Checking GitHub API for latest release: {GITHUB_API_URL}")

    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.v3+json"}

    # Support optional GitHub token for higher rate limits
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    req = urllib.request.Request(GITHUB_API_URL, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise UpdateError(
                "GitHub API rate limit exceeded. Set GITHUB_TOKEN env var to increase limit."
            ) from e
        elif e.code == 404:
            raise UpdateError(
                f"Repository {GITHUB_REPO} not found or no releases published."
            ) from e
        raise UpdateError(f"GitHub API error: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise UpdateError(f"Network error reaching GitHub: {e.reason}") from e

    return {
        "tag_name": data["tag_name"],
        "zipball_url": data["zipball_url"],
        "published_at": data.get("published_at", ""),
        "body": data.get("body", ""),
        "assets": data.get("assets", []),
    }


def _normalize_version(version: str) -> str:
    """Normalize a version string for comparison (strip 'v' prefix)."""
    return version.lstrip("v").strip()


def _is_newer_version(latest: str, current: str) -> bool:
    """Compare two version strings. Returns True if latest > current.

    Uses simple tuple comparison of version parts.
    Falls back to string comparison if parsing fails.
    """
    try:
        latest_parts = tuple(int(x) for x in _normalize_version(latest).split("."))
        current_parts = tuple(int(x) for x in _normalize_version(current).split("."))
        return latest_parts > current_parts
    except (ValueError, AttributeError):
        # Fallback: simple string comparison
        return _normalize_version(latest) != _normalize_version(current)


def _download_release(zipball_url: str, dest_dir: Path) -> Path:
    """Download the release zipball from GitHub.

    Args:
        zipball_url: URL to the release source zip
        dest_dir: Directory to save the downloaded file

    Returns:
        Path to the downloaded zip file
    """
    headers = {"User-Agent": USER_AGENT}
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    zip_path = dest_dir / "release.zip"

    logger.info(f"Downloading release from: {zipball_url}")

    req = urllib.request.Request(zipball_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            with open(zip_path, "wb") as f:
                shutil.copyfileobj(response, f)
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"Failed to download release: {e}") from e

    logger.info(f"Downloaded {zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    return zip_path


def _extract_release(zip_path: Path, dest_dir: Path) -> Path:
    """Extract the release zipball.

    Returns:
        Path to the extracted source directory (contains the zeclock package)
    """
    logger.info("Extracting release archive...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    # GitHub zipball extracts to a directory like "DMDTools-zeClock-<sha>/"
    extracted_dirs = [
        d for d in dest_dir.iterdir() if d.is_dir() and d.name != "__MACOSX"
    ]
    if not extracted_dirs:
        raise UpdateError("No directory found in extracted release archive")

    return extracted_dirs[0]


def _is_overlay_active() -> bool:
    """Check if the root filesystem is using overlayfs (read-only mode)."""
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "/" and parts[2] == "overlay":
                    return True
    except (OSError, PermissionError):
        pass
    return False


def _install_release(source_dir: Path) -> None:
    """Install the new release to the application directory.

    On the Raspberry Pi with overlay filesystem:
    - The app directory is on the read-only lower layer
    - We install to the overlay upper layer (works because overlay is active)
    - Changes persist until next reboot, but zeClock service restarts immediately
    - After reboot, the overlay resets BUT the update re-runs from the timer

    Strategy:
    - Copy new source to /home/zeclock/app (overlay writes to tmpfs upper)
    - Reinstall the package in the venv
    - The next boot will still have the old version (overlay resets)
    - The nightly timer will re-apply the update each boot cycle
    - For true persistence, we also cache the release on /data
    """
    logger.info(f"Installing from {source_dir}...")

    # Verify the source contains the zeclock package
    zeclock_pkg = source_dir / "zeclock"
    if not zeclock_pkg.is_dir():
        raise UpdateError(
            f"Invalid release: no 'zeclock' package directory in {source_dir}"
        )

    # Cache the release on persistent /data for re-application after reboot
    cache_dir = UPDATE_STATE_DIR / "cached-release"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    shutil.copytree(source_dir, cache_dir)
    logger.info(f"Cached release to {cache_dir}")

    # Install to the app directory
    # On overlay FS, this writes to the tmpfs upper layer
    target_app = APP_DIR
    if not target_app.exists():
        # Fallback: maybe running outside the standard RPi layout
        target_app = source_dir  # skip install, just update in-place
        logger.warning(f"App directory {APP_DIR} not found, skipping file copy")
    else:
        # Remove old source and copy new
        old_zeclock = target_app / "zeclock"
        if old_zeclock.exists():
            shutil.rmtree(old_zeclock)

        shutil.copytree(zeclock_pkg, target_app / "zeclock")

        # Copy pyproject.toml for pip install
        pyproject = source_dir / "pyproject.toml"
        if pyproject.exists():
            shutil.copy2(pyproject, target_app / "pyproject.toml")

        logger.info(f"Copied new source to {target_app}")

    # Reinstall the package in the virtualenv
    pip_bin = VENV_DIR / "bin" / "pip"
    if pip_bin.exists():
        logger.info("Reinstalling package in virtualenv...")
        try:
            result = subprocess.run(
                [str(pip_bin), "install", "--no-deps", "-e", str(target_app)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning(f"pip install warning: {result.stderr}")
            else:
                logger.info("Package reinstalled successfully")
        except subprocess.TimeoutExpired:
            logger.warning("pip install timed out, continuing anyway")
        except FileNotFoundError:
            logger.warning("pip not found in venv, skipping reinstall")
    else:
        logger.warning(f"Virtualenv pip not found at {pip_bin}, skipping reinstall")


def _restart_service() -> None:
    """Restart the zeClock systemd service to pick up new code."""
    logger.info("Restarting zeclock.service...")
    try:
        result = subprocess.run(
            ["systemctl", "restart", "zeclock.service"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                f"Service restart returned non-zero: {result.stderr.strip()}"
            )
        else:
            logger.info("Service restarted successfully")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(f"Could not restart service: {e}")


def _apply_cached_update() -> Optional[str]:
    """Re-apply a cached update from /data (used after overlay reset on reboot).

    Returns:
        The version string if applied, None otherwise.
    """
    cache_dir = UPDATE_STATE_DIR / "cached-release"
    if not cache_dir.exists():
        return None

    # Check if the cached version matches what's in the version file
    cached_version = (
        UPDATE_VERSION_FILE.read_text().strip()
        if UPDATE_VERSION_FILE.exists()
        else None
    )
    if not cached_version:
        return None

    # Check if current running code is already at this version
    if _normalize_version(__version__) == _normalize_version(cached_version):
        return None

    logger.info(f"Re-applying cached update v{cached_version} after reboot...")
    try:
        _install_release(cache_dir)
        return cached_version
    except Exception as e:
        logger.error(f"Failed to re-apply cached update: {e}")
        return None


def check_for_update() -> UpdateResult:
    """Check if an update is available without installing it.

    Returns:
        UpdateResult with update availability information.
    """
    current = _get_installed_version()
    release = get_latest_release()
    latest = _normalize_version(release["tag_name"])

    if _is_newer_version(latest, current):
        return UpdateResult(
            updated=False,
            current_version=current,
            latest_version=latest,
            message=f"Update available: {current} -> {latest}",
        )
    else:
        return UpdateResult(
            updated=False,
            current_version=current,
            latest_version=latest,
            message=f"Already up-to-date: {current}",
        )


def perform_update(force: bool = False) -> UpdateResult:
    """Check for and install the latest release.

    Args:
        force: If True, reinstall even if version matches.

    Returns:
        UpdateResult with operation outcome.
    """
    current = _get_installed_version()
    logger.info(f"Current version: {current}")

    # Fetch latest release info
    release = get_latest_release()
    latest = _normalize_version(release["tag_name"])
    logger.info(f"Latest release: {latest} (published: {release['published_at']})")

    # Check if update is needed
    if not force and not _is_newer_version(latest, current):
        msg = f"Already up-to-date at version {current}"
        logger.info(msg)
        return UpdateResult(
            updated=False,
            current_version=current,
            latest_version=latest,
            message=msg,
        )

    logger.info(f"Updating: {current} -> {latest}")

    # Download and install
    temp_dir = Path(tempfile.mkdtemp(prefix="zeclock-ota-"))
    try:
        zip_path = _download_release(release["zipball_url"], temp_dir)
        source_dir = _extract_release(zip_path, temp_dir)
        _install_release(source_dir)
        _save_installed_version(latest)

        # Restart service
        _restart_service()

        msg = f"Successfully updated from {current} to {latest}"
        logger.info(msg)

        # Log update event
        _log_update_event(current, latest, success=True)

        return UpdateResult(
            updated=True,
            current_version=current,
            latest_version=latest,
            message=msg,
        )
    except Exception as e:
        msg = f"Update failed: {e}"
        logger.error(msg)
        _log_update_event(current, latest, success=False, error=str(e))
        raise UpdateError(msg) from e
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _log_update_event(
    from_version: str, to_version: str, success: bool, error: str = ""
) -> None:
    """Append an entry to the update history log."""
    UPDATE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    history_file = UPDATE_STATE_DIR / "history.json"

    history = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text())
        except (json.JSONDecodeError, OSError):
            history = []

    entry = {
        "timestamp": datetime.now().isoformat(),
        "from_version": from_version,
        "to_version": to_version,
        "success": success,
    }
    if error:
        entry["error"] = error

    history.append(entry)

    # Keep only last 50 entries
    history = history[-50:]
    history_file.write_text(json.dumps(history, indent=2))


def main() -> None:
    """CLI entry point for the updater."""
    import argparse

    parser = argparse.ArgumentParser(
        description="zeClock OTA Updater - Automatic updates via GitHub Releases"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check for updates, don't install",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reinstall even if already up-to-date",
    )
    parser.add_argument(
        "--apply-cached",
        action="store_true",
        help="Re-apply cached update from /data (used after reboot on overlay FS)",
    )

    args = parser.parse_args()
    _setup_logging()

    logger.info("=" * 60)
    logger.info(f"zeClock OTA Updater - {datetime.now().isoformat()}")
    logger.info("=" * 60)

    try:
        if args.apply_cached:
            version = _apply_cached_update()
            if version:
                logger.info(f"Re-applied cached update: v{version}")
                _restart_service()
            else:
                logger.info("No cached update to apply")
            return

        if args.check:
            result = check_for_update()
            print(result)
            sys.exit(
                0
                if not _is_newer_version(result.latest_version, result.current_version)
                else 1
            )

        result = perform_update(force=args.force)
        print(result)
        sys.exit(0 if result.updated or not args.force else 1)

    except UpdateError as e:
        logger.error(f"Update error: {e}")
        sys.exit(2)
    except KeyboardInterrupt:
        logger.info("Update cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
