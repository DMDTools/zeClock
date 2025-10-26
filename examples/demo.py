"""
Démo complète : horloge + animation DotClk sur ZeDMD
"""
import asyncio
import time
from pathlib import Path
from zeclock.dmdserver_client import DMDServerClient
from zeclock.readers import load_scene
from zeclock.overlay import overlay_or, create_time_overlay


async def run_animated_clock():
    """Affiche l'heure sur une animation DotClk"""
    
    # Connexion au serveur
    client = DMDServerClient("localhost", 6789)
    if not client.connect():
        print("❌ dmdserver not running!")
        return
    
    # Charger une animation
    scene_path = Path("animations/pinball.scn")
    if scene_path.exists():
        scene = load_scene(scene_path)
        print(f"✅ Loaded scene: {len(scene)} frames")
    else:
        scene = None
    
    try:
        frame_index = 0
        while True:
            # Récupérer la frame d'animation
            if scene:
                anim_frame = scene.get_frame(frame_index)
                frame_index = (frame_index + 1) % len(scene)
            else:
                anim_frame = Image.new('1', (128, 32))
            
            # Créer overlay horloge
            time_str = time.strftime("%H:%M")
            time_img = Image.new('1', (128, 32))
            draw = ImageDraw.Draw(time_img)
            draw.text((40, 8), time_str, font=font, fill=255)
            
            # Fusionner
            merged = overlay_or(anim_frame, time_img)
            
            # Envoyer au ZeDMD
            client.send_monochrome_frame(merged, color=(255, 128, 0))
            
            await asyncio.sleep(0.04)  # 25 FPS
    
    except KeyboardInterrupt:
        print("\n⏹️  Stopping...")
    finally:
        client.disconnect()


if __name__ == "__main__":
    asyncio.run(run_animated_clock())
