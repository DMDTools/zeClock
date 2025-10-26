# zeClock

> 🕒 Une horloge animée intelligente pour afficheur DMD ZeDMD, inspirée du projet DotClk

Transformez votre bureau en salle d'arcade avec une horloge DMD qui affiche l'heure sur des animations rétro de flipper !

![zeClock Demo](https://via.placeholder.com/640x160/1a1a1a/ff8000?text=zeClock+Demo)

## Fonctionnalités

- 🎮 **Animations DotClk natives** : Lecture directe des fichiers `.scn` (2300+ animations disponibles)
- 🔤 **Fonts bitmap DotClk** : Support des polices `.fnt` originales
- 🌐 **Communication WiFi/USB** : Connexion ZeDMD via libdmdutil/dmdserver
- ⚡ **Architecture asynchrone** : Rendu fluide à 25 FPS sans bloquer le CPU
- 🎨 **Overlay intelligent** : Fusion bitwise OR comme le DotClk original
- 🔌 **Mode attract** : Activation automatique après inactivité
- 🚀 **API REST** : Contrôle à distance (changement d'affichage, notifications)
- 📦 **Installation simple** : Scripts automatisés pour tout installer

## Prérequis

- **Python 3.9+**
- **ZeDMD** (128x32 ou 256x64) connecté en USB ou WiFi
- **Linux** (Raspberry Pi, Ubuntu, WSL), **macOS**, ou **Windows** (Git Bash/WSL)

## Installation

**1. Cloner le projet**

```bash
git clone https://github.com/DMDTools/zeclock.git
cd zeclock
```

**2. Installer zeClock**

```bash
pip install -e .
```

**3. Installer libdmdutil (dmdserver)**

```bash
./scripts/install_libdmdutil.sh
# Ou version Python cross-platform :
python3 scripts/install_libdmdutil.py
```

Cela installe :
- `dmdserver` : Serveur TCP pour communiquer avec ZeDMD
- Bibliothèques : `libdmdutil`, `libzedmd`, `libserum`, etc.
- Configuration par défaut : `~/.zeclock/config/dmdserver.ini`

**4. Installer les ressources DotClk (animations + fonts)**

```bash
./scripts/install_dotclk_resources.sh
```

Cela télécharge depuis [sigmafx/DotClk-Resources](https://github.com/sigmafx/DotClk-Resources) :
- **2300+ animations** `.scn` (pinball, classiques, vacances...)
- **Fonts bitmap** `.fnt` DotClk originales

## Démarrage

**Lancer dmdserver (terminal 1)**

```bash
~/.zeclock/bin/dmdserver -c ./config/dmdserver.ini -l -v
```

Options :
- `-a 0.0.0.0` : Écoute sur toutes les interfaces
- `-p 6789` : Port TCP (défaut)
- `-w` : Ne pas quitter si aucun display connecté
- `-l` : Activer les logs

Ou avec fichier de config :

```bash
~/.zeclock/bin/dmdserver -c ~/.zeclock/config/dmdserver.ini -w -l
```

**Lancer zeClock (terminal 2)**

```bash
python -m zeclock.clock
```

Ou avec l'exemple d'animation :

```bash
python examples/zeclock_demo.py
```

## Exemples d'utilisation

**Horloge simple**

```python
from zeclock.clock import ZeClock
import asyncio

clock = ZeClock()
asyncio.run(clock.run())
```

**Horloge avec animation DotClk**

```python
from pathlib import Path
from zeclock.readers import load_scene, load_font
from zeclock.overlay import overlay_or
from zeclock.dmdserver_client import DMDServerClient
import time

# Charger une animation
scene = load_scene(Path("~/.zeclock/resources/animations/Pinball/AFM/attract.scn").expanduser())

# Charger une font
font = load_font(Path("~/.zeclock/resources/Fonts/Font1.fnt").expanduser())

# Connexion au serveur
client = DMDServerClient("localhost", 6789)
client.connect()

# Afficher l'animation avec l'heure
for frame in scene:
    time_str = time.strftime("%H:%M")
    time_overlay = font.render_text(time_str, 128, 32)
    merged = overlay_or(frame, time_overlay)
    client.send_monochrome_frame(merged, color=(255, 128, 0))
    time.sleep(0.04)  # 25 FPS
```

## Configuration

**Variables d'environnement**

```bash
# Dossier des ressources
export ZECLOCK_RESOURCES="$HOME/.zeclock/resources"

# Serveur DMD (si ZeDMD en WiFi)
export DMDSERVER_HOST="192.168.1.100"
export DMDSERVER_PORT="6789"
```

**Fichier de configuration dmdserver**

Éditer `~/.zeclock/config/dmdserver.ini` :

```ini
[DMDServer]
Addr = 0.0.0.0
Port = 6789

[ZeDMD]
Enabled = 1
Device =              # Laisser vide pour auto-détection
Brightness = 10       # 0-15
Debug = 0

[ZeDMD-WiFi]
Enabled = 1
WiFiAddr = 192.168.1.100    # IP de votre ZeDMD WiFi
```

## Structure du projet

```
zeclock/
├── zeclock/
│   ├── __init__.py
│   ├── clock.py                 # Horloge principale
│   ├── config.py                # Configuration
│   ├── dmdserver_client.py      # Client TCP pour dmdserver
│   ├── overlay.py               # Fusion animations/texte
│   ├── readers/
│   │   ├── __init__.py
│   │   ├── fnt_reader.py        # Lecture fonts .fnt
│   │   └── scn_reader.py        # Lecture animations .scn
│   └── resources/
│       └── fonts/
│           └── default.ttf      # Font fallback (Press Start 2P)
├── examples/
│   ├── run_clock.py             # Exemple simple
│   └── zeclock_demo.py          # Exemple avec animations
├── scripts/
│   ├── install_libdmdutil.sh    # Installation libdmdutil
│   ├── install_libdmdutil.py    # Version Python
│   └── install_dotclk_resources.sh
├── setup.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

**Ressources installées**

```
~/.zeclock/
├── bin/
│   ├── dmdserver                # Exécutable principal
│   ├── libdmdutil.so            # Bibliothèques
│   ├── libzedmd.so
│   └── ...
├── config/
│   └── dmdserver.ini            # Configuration
└── resources/
    ├── Fonts/
    │   ├── Font1.fnt            # Font DotClk par défaut
    │   └── Font2.fnt
    └── animations/
        ├── Pinball/             # Animations par thème
        │   ├── AFM/
        │   ├── TronLegacy/
        │   └── ...
        ├── Classic/
        └── Holiday/
```

## Développement

**Installation en mode développement**

```bash
git clone https://github.com/votre-username/zeclock.git
cd zeclock
pip install -e ".[dev]"
```

**Tests**

```bash
pytest tests/
```

**Linter**

```bash
black zeclock/
flake8 zeclock/
```

## Dépannage

**dmdserver ne démarre pas**

```bash
# Vérifier que les bibliothèques sont bien installées
ls ~/.zeclock/bin/

# Vérifier les permissions
chmod +x ~/.zeclock/bin/dmdserver

# Tester avec logs verbeux
dmdserver -v
```

**ZeDMD non détecté**

```bash
# Lister les ports série
ls /dev/ttyUSB* /dev/ttyACM* /dev/cu.usbserial*

# Forcer le port dans dmdserver.ini
[ZeDMD]
Device = /dev/ttyUSB0
```

**Animations ne s'affichent pas**

```bash
# Vérifier que les ressources sont installées
ls ~/.zeclock/resources/animations/

# Réinstaller si nécessaire
./scripts/install_dotclk_resources.sh
```

**Performance / FPS bas**

```python
# Réduire la résolution ou le FPS
clock = ZeClock(width=128, height=32, fps=15)

# Précharger les animations en RAM
scene = load_scene("animation.scn")
frames = list(scene)  # Force le chargement
```

## Roadmap

- [ ] **API REST** : Contrôle via HTTP (changement de clock, notifications)
- [ ] **MQTT** : Intégration domotique (Jeedom, Home Assistant)
- [ ] **Plugins** : Système de plugins Python extensible
  - [ ] WeatherClock : Affichage météo
  - [ ] JeedomClock : Données domotique
  - [ ] MAMEClock : High scores
  - [ ] AWSClock : Coûts AWS
- [ ] **Mode attract avancé** : Rotation aléatoire entre plusieurs clocks
- [ ] **Interface web** : Configuration via navigateur
- [ ] **Galaga Clock** : Animation où Galaga tire sur les chiffres qui changent

## Références

- **DotClk** (inspiration) : [sigmafx/DotClk](https://github.com/sigmafx/DotClk)
- **DotClk Resources** : [sigmafx/DotClk-Resources](https://github.com/sigmafx/DotClk-Resources)
- **libdmdutil** : [vpinball/libdmdutil](https://github.com/vpinball/libdmdutil)
- **ZeDMD** : [PPUC/ZeDMD](https://github.com/PPUC/ZeDMD)
- **ZeDMD OS** : [PPUC/zedmdos](https://github.com/PPUC/zedmdos)

## Licence

MIT License - voir [LICENSE](LICENSE)

## Remerciements

- **SigmaFX** pour le projet DotClk original et ses magnifiques animations
- **vpinball** pour libdmdutil et dmdserver
- **PPUC** pour le hardware ZeDMD
- La communauté **pinball virtuel** pour l'écosystème DMD

## Support

- **Issues** : [GitHub Issues](https://github.com/votre-username/zeclock/issues)
- **Discussions** : [GitHub Discussions](https://github.com/votre-username/zeclock/discussions)
- **Discord** : [Lien Discord communauté pinball]

---

**Fait avec ❤️ par [votre nom] - Inspiré par la magie des flippers rétro** 🎮✨
