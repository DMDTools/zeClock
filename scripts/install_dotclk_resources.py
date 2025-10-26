#!/usr/bin/env python3
"""
Script pour télécharger et installer les ressources DotClk (animations + fonts)
Compatible Linux, macOS, Windows
"""
import urllib.request
import json
import zipfile
import shutil
from pathlib import Path
import sys

GITHUB_REPO = "sigmafx/DotClk-Resources"
RESOURCES_DIR = Path.home() / ".zeclock" / "resources"
TEMP_DIR = Path("/tmp") / "dotclk-resources-install"

# Couleurs ANSI pour l'output (compatible Windows via colorama)
try:
    import colorama
    colorama.init()
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'
except ImportError:
    GREEN = YELLOW = RED = NC = ''


def print_color(color, text):
    """Affiche du texte coloré"""
    print(f"{color}{text}{NC}")


def get_latest_commit_sha():
    """Récupère le SHA du dernier commit sur master"""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/master"
    try:
        with urllib.request.urlopen(api_url) as response:
            data = json.loads(response.read())
            return data["sha"][:7]  # Short SHA
    except Exception as e:
        print_color(YELLOW, f"⚠️  Could not fetch latest commit: {e}")
        return "master"


def download_repository():
    """Télécharge l'archive ZIP du repository"""
    print_color(GREEN, "📦 Downloading DotClk resources...")
    
    # URL de l'archive master
    download_url = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/master.zip"
    
    # Créer le dossier temporaire
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = TEMP_DIR / "dotclk-resources.zip"
    
    print_color(YELLOW, f"🌐 Downloading from: {download_url}")
    
    try:
        # Télécharger avec barre de progression
        def progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(100, block_num * block_size * 100 / total_size)
                sys.stdout.write(f"\r   Progress: {percent:.1f}%")
                sys.stdout.flush()
        
        urllib.request.urlretrieve(download_url, archive_path, progress_hook)
        print()  # Nouvelle ligne après la progression
        print_color(GREEN, "✅ Download complete")
        
    except Exception as e:
        print_color(RED, f"❌ Download failed: {e}")
        sys.exit(1)
    
    return archive_path


def extract_archive(archive_path):
    """Extrait l'archive ZIP"""
    print_color(YELLOW, "📂 Extracting archive...")
    
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(TEMP_DIR)
        print_color(GREEN, "✅ Extraction complete")
    except Exception as e:
        print_color(RED, f"❌ Extraction failed: {e}")
        sys.exit(1)
    
    # Trouver le dossier extrait (DotClk-Resources-master)
    extracted_dirs = list(TEMP_DIR.glob("DotClk-Resources-*"))
    if not extracted_dirs:
        print_color(RED, "❌ Extracted directory not found")
        sys.exit(1)
    
    return extracted_dirs[0]


def install_resources(source_dir):
    """Installe les fonts et animations"""
    print_color(YELLOW, f"📦 Installing resources to: {RESOURCES_DIR}")
    
    # Créer le dossier de destination
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Installer les fonts
    fonts_src = source_dir / "Fonts"
    fonts_dst = RESOURCES_DIR / "Fonts"
    
    if fonts_src.exists():
        if fonts_dst.exists():
            shutil.rmtree(fonts_dst)
        shutil.copytree(fonts_src, fonts_dst)
        font_count = len(list(fonts_dst.glob("*.fnt")))
        print_color(GREEN, f"   ✓ {font_count} fonts installed")
    else:
        print_color(YELLOW, f"   ⚠️  Fonts directory not found: {fonts_src}")
    
    # Installer les animations
    scenes_src = source_dir / "Scenes"
    scenes_dst = RESOURCES_DIR / "animations"
    
    if scenes_src.exists():
        if scenes_dst.exists():
            shutil.rmtree(scenes_dst)
        shutil.copytree(scenes_src, scenes_dst)
        
        # Compter les animations
        scn_count = len(list(scenes_dst.rglob("*.scn")))
        print_color(GREEN, f"   ✓ {scn_count} animations installed")
    else:
        print_color(YELLOW, f"   ⚠️  Scenes directory not found: {scenes_src}")


def create_readme():
    """Crée un README dans le dossier de ressources"""
    readme_path = RESOURCES_DIR / "README.txt"
    
    readme_content = """
DotClk Resources for zeClock
=============================

Ces ressources proviennent du projet DotClk original :
https://github.com/sigmafx/DotClk-Resources

Contenu :
- Fonts/     : Polices bitmap .fnt
- animations/ : Animations .scn (2300+)

Organisation des animations :
- Pinball/    : Animations de machines de pinball
- Classic/    : Animations classiques
- Holiday/    : Animations de fêtes
- et plus...

Pour ajouter vos propres animations, copiez vos fichiers .scn
dans le dossier animations/ ou créez des sous-dossiers.

License : Voir le repository DotClk-Resources original
"""
    
    readme_path.write_text(readme_content.strip())
    print_color(GREEN, f"   ✓ README created")


def cleanup():
    """Nettoie les fichiers temporaires"""
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
        print_color(GREEN, "🧹 Cleanup complete")


def main():
    """Fonction principale"""
    print_color(GREEN, "╔════════════════════════════════════════════╗")
    print_color(GREEN, "║  📦 DotClk Resources Installer            ║")
    print_color(GREEN, "╚════════════════════════════════════════════╝")
    print()
    
    try:
        # Télécharger
        archive_path = download_repository()
        
        # Extraire
        source_dir = extract_archive(archive_path)
        
        # Installer
        install_resources(source_dir)
        
        # Créer README
        create_readme()
        
        # Nettoyer
        cleanup()
        
        print()
        print_color(GREEN, "╔════════════════════════════════════════════╗")
        print_color(GREEN, "║  ✅ Installation successful!              ║")
        print_color(GREEN, "╚════════════════════════════════════════════╝")
        print()
        print_color(YELLOW, "📍 Resources installed in:")
        print(f"   {RESOURCES_DIR}")
        print()
        print_color(YELLOW, "📂 Available directories:")
        print(f"   - Fonts:      {RESOURCES_DIR / 'Fonts'}")
        print(f"   - Animations: {RESOURCES_DIR / 'animations'}")
        print()
        
    except KeyboardInterrupt:
        print()
        print_color(YELLOW, "⏹️  Installation cancelled by user")
        cleanup()
        sys.exit(1)
    except Exception as e:
        print_color(RED, f"❌ Installation failed: {e}")
        cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
