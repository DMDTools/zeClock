"""
Test des readers DotClk
"""
from pathlib import Path
from zeclock.readers import load_font, load_scene
from zeclock.overlay import overlay_or, create_time_overlay
import time

# Chemins
fonts_dir = Path("fonts")
scenes_dir = Path("animations")

# 1. Charger une fonte
font = load_font(fonts_dir / "dotclk.fnt")
print(f"Font loaded: {font.name}, {font.char_width}x{font.char_height}")

# 2. Charger une animation
scene = load_scene(scenes_dir / "pinball.scn")
print(f"Scene loaded: {len(scene)} frames")

# 3. Afficher l'horloge sur l'animation
for i, frame in enumerate(scene):
    # Créer l'overlay d'horloge
    time_str = time.strftime("%H:%M")
    time_overlay = create_time_overlay(time_str, font)
    
    # Fusionner
    merged = overlay_or(frame, time_overlay)
    
    # Afficher ou envoyer au ZeDMD
    merged.show()  # Pour test
    time.sleep(0.04)  # 25 FPS
    
    if i > 100:  # Limiter pour le test
        break
