"""
Setup script pour zeClock
Installe automatiquement libdmdutil et les ressources DotClk
"""
from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.develop import develop
import subprocess
import sys
from pathlib import Path


class PostInstallCommand(install):
    """Post-installation : télécharge libdmdutil et ressources DotClk"""
    
    def run(self):
        install.run(self)
        self._post_install()
    
    def _post_install(self):
        """Exécute les scripts d'installation"""
        scripts_dir = Path(__file__).parent / "scripts"
        
        print("\n" + "="*60)
        print("📦 Installing zeClock dependencies...")
        print("="*60 + "\n")
        
        # 1. Installer libdmdutil
        print("🔧 Step 1/2: Installing libdmdutil (dmdserver)...\n")
        try:
            subprocess.check_call([
                sys.executable,
                str(scripts_dir / "install_libdmdutil.py")
            ])
            print("\n✅ libdmdutil installed successfully\n")
        except subprocess.CalledProcessError as e:
            print(f"\n⚠️  libdmdutil installation failed: {e}")
            print("You can install it manually later with:")
            print(f"  python {scripts_dir / 'install_libdmdutil.py'}\n")
        
        # 2. Installer les ressources DotClk
        print("🎨 Step 2/2: Installing DotClk resources (animations + fonts)...\n")
        try:
            subprocess.check_call([
                sys.executable,
                str(scripts_dir / "install_dotclk_resources.py")
            ])
            print("\n✅ DotClk resources installed successfully\n")
        except subprocess.CalledProcessError as e:
            print(f"\n⚠️  DotClk resources installation failed: {e}")
            print("You can install them manually later with:")
            print(f"  python {scripts_dir / 'install_dotclk_resources.py'}\n")
        
        print("="*60)
        print("✅ zeClock installation complete!")
        print("="*60)
        print("\n🚀 Quick start:")
        print("  1. Start dmdserver:")
        print("     dmdserver -a 0.0.0.0 -p 6789 -w -l")
        print("  2. Start zeClock:")
        print("     python -m zeclock.clock")
        print()


class PostDevelopCommand(develop):
    """Post-develop : télécharge libdmdutil et ressources DotClk"""
    
    def run(self):
        develop.run(self)
        # Réutiliser la même logique que PostInstallCommand
        PostInstallCommand._post_install(self)


# Lire le README pour la description longue
def read_readme():
    readme_path = Path(__file__).parent / "README.md"
    if readme_path.exists():
        return readme_path.read_text(encoding="utf-8")
    return "Smart DMD clock for ZeDMD inspired by DotClk"


setup(
    name="zeclock",
    version="0.1.0",
    author="Olivier Jacques",
    author_email="your.email@example.com",
    description="Smart DMD clock for ZeDMD inspired by DotClk",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/zeclock",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Games/Entertainment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Operating System :: Microsoft :: Windows",
    ],
    python_requires=">=3.9",
    install_requires=[
        "Pillow>=9.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "black>=22.0",
            "flake8>=4.0",
            "mypy>=0.950",
        ],
    },
    entry_points={
        "console_scripts": [
            "zeclock=zeclock.clock:main",
        ],
    },
    package_data={
        "zeclock": [
            "resources/fonts/*.ttf",
        ],
    },
    cmdclass={
        "install": PostInstallCommand,
        "develop": PostDevelopCommand,
    },
    scripts=[
        "scripts/install_libdmdutil.py",
        "scripts/install_dotclk_resources.py",
    ],
)
