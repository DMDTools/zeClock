"""
Horloge principale zeClock avec support DMDServer
"""
import asyncio
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .dmdserver_client import DMDServerClient
from .readers import load_font, load_scene
from .overlay import overlay_or


class ZeClock:
    """Horloge animée avec affichage sur ZeDMD via DMDServer"""
    
    def __init__(
        self,
        width: int = 128,
        height: int = 32,
        fps: int = 25,
        dmdserver_host: str = "localhost",
        dmdserver_port: int = 6789
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.running = True
        
        # Client DMDServer
        self.dmd_client = DMDServerClient(dmdserver_host, dmdserver_port)
        
        # Charger une font par défaut
        self.font_path = Path(__file__).parent / "fonts" / "default.ttf"
        if self.font_path.exists():
            self.font = ImageFont.truetype(str(self.font_path), 16)
        else:
            self.font = ImageFont.load_default()
    
    async def run(self):
        """Boucle principale asynchrone"""
        if not self.dmd_client.connect():
            print("❌ Cannot start: dmdserver not available")
            return
        
        frame_time = 1 / self.fps
        print(f"🕒 Starting zeClock at {self.fps} FPS")
        
        try:
            while self.running:
                t0 = time.monotonic()
                
                # Générer et envoyer la frame
                frame = self.render_time_frame()
                self.dmd_client.send_monochrome_frame(
                    frame,
                    color=(255, 128, 0)  # Couleur DMD orange classique
                )
                
                # Attente adaptive pour maintenir le FPS
                elapsed = time.monotonic() - t0
                await asyncio.sleep(max(0, frame_time - elapsed))
        
        except KeyboardInterrupt:
            print("\n⏹️  Stopping zeClock...")
        finally:
            self.dmd_client.disconnect()
    
    def render_time_frame(self) -> Image.Image:
        """Génère une frame avec l'heure actuelle"""
        now = time.strftime("%H:%M", time.localtime())
        
        img = Image.new("1", (self.width, self.height))
        draw = ImageDraw.Draw(img)
        
        # Calculer la position centrée
        bbox = draw.textbbox((0, 0), now, font=self.font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        x = (self.width - text_w) // 2
        y = (self.height - text_h) // 2
        
        draw.text((x, y), now, font=self.font, fill=255)
        
        return img


def main():
    """Point d'entrée principal"""
    clock = ZeClock()
    asyncio.run(clock.run())


if __name__ == "__main__":
    main()
