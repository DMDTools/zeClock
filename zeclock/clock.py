"""
Horloge principale zeClock avec support DMDServer
"""
import asyncio
import time
import random
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
        
        # Animation state
        self.scene_files = list(Path.home().glob(".zeclock/resources/animations/*.scn"))
        self.current_scene = None
        self.scene_frame_index = 0
        self.last_scene_change = 0
        self.scene_duration = 10.0  # 10 seconds per scene
        
        # Load DotClk font first, fallback to TTF
        self.dotclk_font = None
        dotclk_font_path = Path.home() / ".zeclock" / "resources" / "Fonts" / "STANDARD.fnt"
        if dotclk_font_path.exists():
            try:
                self.dotclk_font = load_font(dotclk_font_path)
                print(f"✅ Loaded DotClk font: {self.dotclk_font.name}")
            except Exception as e:
                print(f"⚠️ Failed to load DotClk font: {e}")
        
        # Fallback TTF font
        if not self.dotclk_font:
            self.font_path = Path(__file__).parent / "resources" / "fonts" / "default.ttf"
            if self.font_path.exists():
                self.font = ImageFont.truetype(str(self.font_path), 16)
            else:
                self.font = ImageFont.load_default()
        
        # Load first scene if available
        if self.scene_files:
            print(f"🎬 Found {len(self.scene_files)} scene files")
            self._load_new_scene()
        else:
            print("⚠️ No scene files found")
    
    async def run(self):
        """Boucle principale asynchrone"""
        if not self.dmd_client.connect():
            print("❌ Cannot start: dmdserver not available")
            return
        
        # Use scene-specific timing if available, otherwise default FPS
        if self.current_scene and hasattr(self.current_scene, 'frame_delay_ms'):
            frame_time = self.current_scene.frame_delay_ms / 1000.0  # Convert ms to seconds
            actual_fps = 1000.0 / self.current_scene.frame_delay_ms
            print(f"🕒 Starting zeClock with scene timing: {self.current_scene.frame_delay_ms}ms ({actual_fps:.1f} FPS)")
        else:
            frame_time = 1 / self.fps
            print(f"🕒 Starting zeClock at {self.fps} FPS")
        
        try:
            while self.running:
                t0 = time.monotonic()
                
                # Check if we need to change scene (every 10 seconds)
                now = time.time()
                if now - self.last_scene_change >= self.scene_duration:
                    self._load_new_scene()
                    self.last_scene_change = now
                    # Update frame timing for new scene
                    if self.current_scene and hasattr(self.current_scene, 'frame_delay_ms'):
                        frame_time = self.current_scene.frame_delay_ms / 1000.0
                        actual_fps = 1000.0 / self.current_scene.frame_delay_ms
                        print(f"🎬 New scene timing: {self.current_scene.frame_delay_ms}ms ({actual_fps:.1f} FPS)")
                
                # Create clock frame
                frame = self.create_clock_frame()
                
                # Send to DMD
                success = self.dmd_client.send_frame(frame)
                
                # Reconnect if sending failed
                if not success:
                    print("⚠️ Reconnecting to dmdserver...")
                    self.dmd_client.disconnect()
                    if not self.dmd_client.connect():
                        print("❌ Cannot reconnect to dmdserver")
                        break
                
                # Frame timing
                elapsed = time.monotonic() - t0
                sleep_time = max(0, frame_time - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            print("\n🛑 Stopping zeClock...")
        finally:
            self.dmd_client.disconnect()
    
    def create_clock_frame(self) -> Image.Image:
        """Create a clock frame with current time and optional animation"""
        current_time = time.strftime("%H:%M")
        
        # Check if we need to change scene (every 10 seconds)
        now = time.time()
        if now - self.last_scene_change >= self.scene_duration:
            self._load_new_scene()
            self.last_scene_change = now
        
        # Get animation frame if available
        animation_frame = None
        if self.current_scene and len(self.current_scene.frames) > 0:
            animation_frame = self.current_scene.frames[self.scene_frame_index % len(self.current_scene.frames)]
            self.scene_frame_index += 1
        
        # Create clock overlay
        if self.dotclk_font:
            clock_overlay = self.dotclk_font.render_text(current_time, self.width, self.height)
            
            # Combine animation and clock if both exist
            if animation_frame:
                try:
                    merged_frame = overlay_or(animation_frame, clock_overlay)
                except Exception as e:
                    print(f"⚠️ Overlay error: {e}")
                    merged_frame = clock_overlay
            else:
                merged_frame = clock_overlay
            
            # Fast RGB conversion using numpy-style operations
            import numpy as np
            gray_array = np.array(merged_frame)
            
            # Create RGB array with orange color mapping
            rgb_array = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            mask = gray_array > 0
            intensity = gray_array[mask] / 255.0
            
            rgb_array[mask, 0] = (255 * intensity).astype(np.uint8)  # Red
            rgb_array[mask, 1] = (128 * intensity).astype(np.uint8)  # Green
            rgb_array[mask, 2] = 0  # Blue
            
            return Image.fromarray(rgb_array, 'RGB')
        
        # Fallback to TTF font (no animation support)
        img = Image.new('RGB', (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        bbox = draw.textbbox((0, 0), current_time, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (self.width - text_width) // 2
        y = (self.height - text_height) // 2
        
        draw.text((x, y), current_time, font=self.font, fill=(255, 128, 0))
        
        return img
    
    def _load_new_scene(self):
        """Load a random scene"""
        if self.scene_files:
            scene_path = random.choice(self.scene_files)
            try:
                self.current_scene = load_scene(scene_path, self.width, self.height)
                self.scene_frame_index = 0
                print(f"🎬 Loaded scene: {scene_path.name} ({len(self.current_scene.frames)} frames)")
            except Exception as e:
                print(f"⚠️ Failed to load scene {scene_path.name}: {e}")
                self.current_scene = None
    
    def stop(self):
        """Stop the clock"""
        self.running = False


def main():
    """Point d'entrée principal"""
    clock = ZeClock()
    asyncio.run(clock.run())


if __name__ == "__main__":
    main()
