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
from .overlay import overlay_or, overlay_or_rgb


class ZeClock:
    """Horloge animée avec affichage sur ZeDMD via DMDServer"""
    
    def __init__(
        self,
        width: int = 128,
        height: int = 32,
        fps: int = 25,
        dmdserver_host: str = "localhost",
        dmdserver_port: int = 6789,
        test_mode: bool = False,
        color: str = "orange",
        animation_color: str = None
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.running = True
        
        # Color mapping
        self.colors = [
            (255, 128, 0),   # orange
            (0, 128, 255),   # blue
            (255, 0, 0),     # red
            (255, 0, 255),   # purple
            (0, 255, 128),   # green
            (255, 255, 0),   # yellow
            (0, 255, 255),   # cyan
            (255, 64, 128)   # pink
        ]
        color_map = {"orange": 0, "blue": 1, "red": 2, "purple": 3, "green": 4, "yellow": 5, "cyan": 6, "pink": 7}
        self.color_mode = color
        if color == "auto":
            self.color = self.colors[0]
            self.last_color_change = time.time()
        else:
            self.color = self.colors[color_map.get(color, 0)]
        
        # Animation color (defaults to same as clock if not specified)
        self.animation_color = self.colors[color_map.get(animation_color, 0)] if animation_color else self.color
        
        # Client DMDServer
        self.dmd_client = DMDServerClient(dmdserver_host, dmdserver_port)
        
        # Animation state
        if test_mode:
            test_scenes = ["RD1500.scn"] #, "RD1245.scn", "RD1893.scn", "RD1719.scn"]
            all_scenes = list(Path.home().glob(".zeclock/resources/animations/**/*.scn"))
            self.scene_files = [s for s in all_scenes if s.name in test_scenes]
        else:
            self.scene_files = list(Path.home().glob(".zeclock/resources/animations/**/*.scn"))
        self.current_scene = None
        self.scene_frame_index = 0
        self.precomputed_frames = []
        self.precomputed_frames_noblink = []
        self.precomputing = False
        self.millis_scene_start = 0
        self.millis_scene_frame_delay = 0
        self.cur_scene = 0
        self.scene_start = 0
        self.scene_duration = 0
        self.cfg_clock_delay_value = 5000  # 5 seconds default
        self.animation_playing = False
        
        # State machine
        self.do_first = 0  # 0=NA, 1=TODO, 2=INPROC, 3=DONE
        self.do_last = 0
        self.frame_start_time = 0
        
        # Clock caching
        self.cached_clock_frame = None
        self.last_clock_time = ""
        self.current_clock_style = 0  # Track current clock style
        
        # Load font
        self.dotclk_font = None
        font_path = Path.home() / ".zeclock" / "resources" / "Fonts" / "STANDARD.fnt"
        if font_path.exists():
            try:
                self.dotclk_font = load_font(font_path)
                print(f"✅ Loaded font: {self.dotclk_font.name}")
            except Exception as e:
                print(f"⚠️ Failed to load font: {e}")
        else:
            print("❌ No font found")
        
        # Load first scene if available
        if self.scene_files:
            print(f"🎬 Found {len(self.scene_files)} scene files")
            self.scene_end_time = time.time()
            # Initialize with standard clock style
            self.current_clock_style = 0
        else:
            print("⚠️ No scene files found")
            # Initialize with standard clock style
            self.current_clock_style = 0
    
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
                
                # Check if we need to start new animation (5s after last one ended)
                now = time.time()
                if not self.animation_playing and not self.precomputing and now - self.scene_end_time >= 5:
                    asyncio.create_task(self._precompute_animation())
                
                # Change color every minute if auto mode
                if self.color_mode == "auto" and now - self.last_color_change >= 60:
                    self.color = self.colors[int(now // 60) % len(self.colors)]
                    self.last_color_change = now
                    self.last_clock_time = ""  # Force refresh
                
                # Create DMD frame (clock + animation)
                frame = self.create_dmd_frame()
                
                # Send to DMD
                success = self.dmd_client.send_frame(frame)
                
                # Reconnect if sending failed
                if not success:
                    print("⚠️ Reconnecting to dmdserver...")
                    self.dmd_client.disconnect()
                    if not self.dmd_client.connect():
                        print("❌ Cannot reconnect to dmdserver")
                        break
                
                # Use scene-specific timing
                if self.animation_playing and self.current_scene:
                    frame_time = (self.current_scene.frame_delay_ms if self.current_scene.frame_delay_ms > 0 else 40) / 1000.0
                else:
                    frame_time = 0.5  # Refresh every 500ms for colon blinking
                
                # Frame timing
                elapsed = time.monotonic() - t0
                sleep_time = max(0, frame_time - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            print("\n🛑 Stopping zeClock...")
        finally:
            self.dmd_client.disconnect()
    
    def create_dmd_frame(self) -> Image.Image:
        """Create a DMD frame with current time and optional animation"""
        # If precomputed animation is available, use it directly
        if self.animation_playing and self.precomputed_frames:
            if self.scene_frame_index < len(self.precomputed_frames):
                # Alternate between blink/noblink every 500ms
                elapsed_ms = int((time.time() - self.animation_start_time) * 1000)
                blink_state = (elapsed_ms // 500) % 2
                frame = self.precomputed_frames[self.scene_frame_index] if blink_state == 0 else self.precomputed_frames_noblink[self.scene_frame_index]
                self.scene_frame_index += 1
                return frame
            else:
                # Animation finished
                self.animation_playing = False
                self.precomputed_frames = []
                self.precomputed_frames_noblink = []
                self.current_scene = None
                self.current_clock_style = 0
                self.last_clock_time = ""
                self.scene_end_time = time.time()
        
        # Generate clock with 500ms blink timing
        milliseconds = int(time.time() * 1000)
        blink_state = (milliseconds // 500) % 2
        cache_key = f"{time.strftime('%H:%M:%S')}_{blink_state}"
        
        if cache_key != self.last_clock_time:
            # Second beat - alternate colon display every 500ms
            if blink_state == 0:
                # Show the colon dots
                display_time = time.strftime("%H:%M")
            else:
                # Hide the colon dots (use space)
                display_time = time.strftime("%H %M")
            
            # Generate clock dotmap based on current clock style (set at animation start)
            if self.current_clock_style == 1:  # ClockStyleCustom
                # Custom positioning - remove AM/PM
                if len(display_time) > 5:
                    display_time = display_time[:5]  # Truncate AM/PM
                
                # Use menu font for custom style (smaller font)
                text_width = self.dotclk_font.get_text_width(display_time)
                text_height = self.dotclk_font.char_height
                
                # Calculate position from custom coordinates (center at custom point)
                x_pos = self.current_scene.custom_x - (text_width // 2) if self.current_scene else 64
                y_pos = self.current_scene.custom_y - (text_height // 2) if self.current_scene else 16
                
                # Create blank canvas and paste text at custom position
                self.cached_clock_frame = Image.new('L', (self.width, self.height), 0)
                text_img = self.dotclk_font.render_text(display_time, text_width, text_height)
                
                # Ensure position is within bounds
                x_pos = max(0, min(x_pos, self.width - text_width))
                y_pos = max(0, min(y_pos, self.height - text_height))
                
                self.cached_clock_frame.paste(text_img, (x_pos, y_pos))
                
                # Reposition mask to full canvas
                if hasattr(text_img, 'mask_data'):
                    import numpy as np
                    full_mask = np.zeros((self.height, self.width), dtype=np.uint8)
                    text_mask_bytes = np.frombuffer(text_img.mask_data, dtype=np.uint8)
                    text_mask = np.unpackbits(text_mask_bytes, bitorder='little').reshape(text_height, -1)[:, :text_width]
                    full_mask[y_pos:y_pos+text_height, x_pos:x_pos+text_width] = text_mask
                    mask_packed = np.packbits(full_mask.reshape(-1, self.width), axis=1, bitorder='little')
                    self.cached_clock_frame.mask_data = mask_packed.tobytes()
                    self.cached_clock_frame.mask_width_bytes = (self.width // 8) + (1 if self.width % 8 else 0)
            else:
                # ClockStyleStd (0) - Standard centered positioning
                self.cached_clock_frame = self.dotclk_font.render_text(display_time, self.width, self.height)
            
            self.last_clock_time = cache_key
        
        clock_frame = self.cached_clock_frame
        
        # Get animation frame if playing
        animation_frame = None
        show_blank_frame = False
        
        if self.animation_playing and self.current_scene and len(self.current_scene.frames) > 0:
            # State machine logic for first/last frame handling
            if self.do_first == 1:  # TODO
                self.do_first = 2  # INPROC
                self.frame_start_time = time.time()
                if self.current_scene.first_blank:
                    show_blank_frame = True
                else:
                    animation_frame = self.current_scene.frames[0] if len(self.current_scene.frames) > 0 else None
            elif self.do_first == 2:  # INPROC
                # First frame delay period
                if time.time() - self.frame_start_time >= self.current_scene.first_frame_delay / 1000.0:
                    self.do_first = 3  # DONE
                    self.scene_frame_index = 0
                else:
                    if self.current_scene.first_blank:
                        show_blank_frame = True
                    else:
                        animation_frame = self.current_scene.frames[0] if len(self.current_scene.frames) > 0 else None
            elif self.scene_frame_index < len(self.current_scene.frames):
                # Normal frame playback
                animation_frame = self.current_scene.frames[self.scene_frame_index]
                self.scene_frame_index += 1
            else:
                # All frames played - check for last frame handling
                if self.do_last == 1:  # TODO
                    self.do_last = 2  # INPROC
                    self.frame_start_time = time.time()
                    if self.current_scene.last_blank:
                        show_blank_frame = True
                    else:
                        animation_frame = self.current_scene.frames[-1] if len(self.current_scene.frames) > 0 else None
                elif self.do_last == 2:  # INPROC
                    # Last frame delay period
                    if time.time() - self.frame_start_time >= self.current_scene.last_frame_delay / 1000.0:
                        self.animation_playing = False
                        self.current_scene = None
                        self.current_clock_style = 0
                        self.last_clock_time = ""
                        self.scene_end_time = time.time()
                    else:
                        if self.current_scene.last_blank:
                            show_blank_frame = True
                        else:
                            animation_frame = self.current_scene.frames[-1] if len(self.current_scene.frames) > 0 else None
                else:
                    # Animation finished - reset to standard clock style
                    self.animation_playing = False
                    self.current_scene = None
                    self.current_clock_style = 0  # Reset to standard
                    self.last_clock_time = ""  # Force clock regeneration
                    self.scene_end_time = time.time()  # Record when scene ended
        
        # Create final frame with dual colors
        if show_blank_frame:
            # During blank periods, show clock only
            import numpy as np
            gray_array = np.array(clock_frame)
            rgb_array = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            intensity = gray_array / 255.0
            for i in range(3):
                rgb_array[:, :, i] = (self.color[i] * intensity).astype(np.uint8)
            return Image.fromarray(rgb_array, 'RGB')
        elif animation_frame:
            # Animation is active - apply layering with dual colors
            if hasattr(self.current_scene, 'frame_layer') and self.current_scene.frame_layer == 1:
                # Clock above animation: animation_color for base, clock_color for overlay
                return overlay_or_rgb(animation_frame, clock_frame, self.animation_color, self.color)
            else:
                # Clock behind animation: clock_color for base, animation_color for overlay
                return overlay_or_rgb(clock_frame, animation_frame, self.color, self.animation_color)
        else:
            # No animation - show only clock
            import numpy as np
            gray_array = np.array(clock_frame)
            rgb_array = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            intensity = gray_array / 255.0
            for i in range(3):
                rgb_array[:, :, i] = (self.color[i] * intensity).astype(np.uint8)
            return Image.fromarray(rgb_array, 'RGB')
    
    async def _precompute_animation(self):
        """Precomputes all DMD frames of an animation in the background"""
        if not self.scene_files:
            return
        
        self.precomputing = True
        scene_path = random.choice(self.scene_files)
        
        print(f"🎯 Loading scene: {scene_path.name}")
        try:
            scene = load_scene(scene_path, self.width, self.height)
        except Exception as e:
            print(f"⚠️ Failed to load scene {scene_path.name}: {e}")
            self.precomputing = False
            return
        
        print(f"⚙️ Pre-computing {len(scene.frames)} frames...")
        print(f"   📊 Storyboard: first_delay={scene.first_frame_delay}ms, frame_delay={scene.frame_delay_ms}ms, last_delay={scene.last_frame_delay}ms")
        print(f"   🎭 Blank frames: first={scene.first_blank}, last={scene.last_blank}")
        print(f"   🔧 State machine: do_first={scene.do_first}, do_last={scene.do_last}")
        print(f"   🎨 Frame layer: {scene.frame_layer} (0=clock behind, 1=clock above)")
        
        import numpy as np
        precomputed_blink = []
        precomputed_noblink = []
        
        # Helper to create a frame  
        def create_frame(animation_frame, display_time, debug=False):
            if scene.clock_style == 1:
                text_width = self.dotclk_font.get_text_width(display_time)
                text_height = self.dotclk_font.char_height
                x_pos = max(0, min(scene.custom_x - (text_width // 2), self.width - text_width))
                y_pos = max(0, min(scene.custom_y - (text_height // 2), self.height - text_height))
                clock_frame = Image.new('L', (self.width, self.height), 0)
                text_img = self.dotclk_font.render_text(display_time, text_width, text_height)
                clock_frame.paste(text_img, (x_pos, y_pos))
                # Reposition mask to full canvas
                if hasattr(text_img, 'mask_data'):
                    full_mask = np.zeros((self.height, self.width), dtype=np.uint8)
                    text_mask_bytes = np.frombuffer(text_img.mask_data, dtype=np.uint8)
                    text_mask = np.unpackbits(text_mask_bytes, bitorder='little').reshape(text_height, -1)[:, :text_width]
                    full_mask[y_pos:y_pos+text_height, x_pos:x_pos+text_width] = text_mask
                    mask_packed = np.packbits(full_mask.reshape(-1, self.width), axis=1, bitorder='little')
                    clock_frame.mask_data = mask_packed.tobytes()
                    clock_frame.mask_width_bytes = (self.width // 8) + (1 if self.width % 8 else 0)
            else:
                clock_frame = self.dotclk_font.render_text(display_time, self.width, self.height)
            

            
            # Apply dual colors
            if hasattr(scene, 'frame_layer') and scene.frame_layer == 1:
                merged_frame = overlay_or_rgb(animation_frame, clock_frame, self.animation_color, self.color)
            else:
                merged_frame = overlay_or_rgb(clock_frame, animation_frame, self.color, self.animation_color)
            
            # Debug RGB
            if debug:
                rgb_array = np.array(merged_frame)
                r_channel = rgb_array[:, :, 0]
                g_channel = rgb_array[:, :, 1]
                black_pixels = np.count_nonzero((r_channel == 0) & (g_channel == 0))
                print(f"   🎨 RGB: black={black_pixels}, clock_color={self.color}, animation_color={self.animation_color}")
            
            return merged_frame
        
        # Debug clock mask and pixels
        test_clock = self.dotclk_font.render_text(time.strftime("%H:%M"), self.width, self.height)
        has_clock_mask = hasattr(test_clock, 'mask_data') and test_clock.mask_data is not None
        clock_arr = np.array(test_clock)
        unique_vals = np.unique(clock_arr)
        print(f"   🔤 Clock mask: present={has_clock_mask}")
        print(f"   🎨 Clock unique pixel values: {unique_vals.tolist()}")
        print(f"   🎨 Clock pixels: 32={np.count_nonzero(clock_arr == 32)}, 96={np.count_nonzero(clock_arr == 96)}, 255={np.count_nonzero(clock_arr == 255)}")
        if has_clock_mask:
            mask_bits = np.frombuffer(test_clock.mask_data, dtype=np.uint8)
            print(f"   🔤 Clock mask: {np.count_nonzero(mask_bits)} non-zero bytes")
        
        # Precompute 2 versions of each frame
        for frame_idx, animation_frame in enumerate(scene.frames):
            if frame_idx == 0:
                has_mask = hasattr(animation_frame, 'mask_data') and animation_frame.mask_data is not None
                anim_array = np.array(animation_frame)
                non_zero = np.count_nonzero(anim_array)
                anim_unique = np.unique(anim_array)
                print(f"   🖼️ Frame 0: size={animation_frame.size}, has_mask={has_mask}, unique_values={anim_unique.tolist()}, non_zero={non_zero}")
            
            precomputed_blink.append(create_frame(animation_frame, time.strftime("%H:%M"), debug=(frame_idx==0)))
            precomputed_noblink.append(create_frame(animation_frame, time.strftime("%H %M")))
            
            if frame_idx % 10 == 0:
                await asyncio.sleep(0)
        
        # Add first/last delay frames
        frame_delay = scene.frame_delay_ms if scene.frame_delay_ms > 0 else 40
        
        if scene.first_frame_delay > 0:
            first_frame_count = int(scene.first_frame_delay / frame_delay)
            precomputed_blink = [precomputed_blink[0]] * first_frame_count + precomputed_blink
            precomputed_noblink = [precomputed_noblink[0]] * first_frame_count + precomputed_noblink
        
        if scene.last_frame_delay > 0:
            last_frame_count = int(scene.last_frame_delay / frame_delay)
            precomputed_blink = precomputed_blink + [precomputed_blink[-1]] * last_frame_count
            precomputed_noblink = precomputed_noblink + [precomputed_noblink[-1]] * last_frame_count
        
        # Activate animation
        self.precomputed_frames = precomputed_blink
        self.precomputed_frames_noblink = precomputed_noblink
        self.current_scene = scene
        self.scene_frame_index = 0
        self.animation_playing = True
        self.animation_start_time = time.time()
        self.current_clock_style = scene.clock_style
        self.last_clock_time = ""
        self.precomputing = False
        
        fps = 1000.0 / scene.frame_delay_ms if scene.frame_delay_ms > 0 else 25.0
        total_duration = len(precomputed_blink) * (scene.frame_delay_ms if scene.frame_delay_ms > 0 else 40) / 1000.0
        print(f"✅ Animation ready: {scene_path.name} ({len(precomputed_blink)} total frames, {fps:.1f} FPS, {total_duration:.1f}s total)")
    
    def _start_new_animation(self):
        """Start a new animation"""
        if self.scene_files:
            scene_path = random.choice(self.scene_files)
            print(f"🎯 Testing scene: {scene_path.name}")
            try:
                self.current_scene = load_scene(scene_path, self.width, self.height)
                self.scene_frame_index = 0
                self.animation_playing = True
                if len(self.current_scene.frames) == 1:
                    self.single_frame_start = time.time()
                
                # Initialize state machine
                self.do_first = self.current_scene.do_first
                self.do_last = self.current_scene.do_last
                
                # Set clock style at animation start
                self.current_clock_style = self.current_scene.clock_style
                # Force clock regeneration with new style
                self.last_clock_time = ""
                
                # Show timing info with clock style
                fps = 1000.0 / self.current_scene.frame_delay_ms if self.current_scene.frame_delay_ms > 0 else 0
                clock_style_name = ["Standard", "Custom"][min(self.current_scene.clock_style, 1)]
                print(f"🎬 Testing animation: {scene_path.name} ({len(self.current_scene.frames)} frames, {self.current_scene.frame_delay_ms}ms, {fps:.1f} FPS, Clock: {clock_style_name})")
                print(f"   Frame layer: {'Above' if getattr(self.current_scene, 'frame_layer', 0) == 1 else 'Behind'} animation")
                if self.current_scene.clock_style == 1:
                    print(f"   Custom clock position: ({self.current_scene.custom_x}, {self.current_scene.custom_y})")
                if hasattr(self.current_scene, 'frame_layer'):
                    layer_name = "Behind" if self.current_scene.frame_layer == 0 else "Above"
                    print(f"   Clock layer: {layer_name} animation")
                
                # Show blank frame info from storyboard
                blank_info = []
                if self.current_scene.first_blank:
                    blank_info.append("First")
                if self.current_scene.last_blank:
                    blank_info.append("Last")
                if blank_info:
                    print(f"   Blank frames: {', '.join(blank_info)}")
            except Exception as e:
                print(f"⚠️ Failed to load scene {scene_path.name}: {e}")
                self.current_scene = None
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
    import argparse
    import sys
    from .installer import check_and_install_resources
    
    parser = argparse.ArgumentParser(description="zeClock - Animated DMD clock")
    parser.add_argument("--color", choices=["orange", "blue", "red", "purple", "green", "yellow", "cyan", "pink", "auto"], default="auto", help="Clock color (default: auto-rotate every minute)")
    parser.add_argument("--animation-color", choices=["orange", "blue", "red", "purple", "green", "yellow", "cyan", "pink"], help="Animation color (default: same as clock)")
    parser.add_argument("--bootstrap", action="store_true", help="Automatically install dmdserver and all resources without running the clock")
    parser.add_argument("--no-prompt", action="store_true", help="Disable interactive prompt during automatic bootstrap")
    args = parser.parse_args()
    
    # If --bootstrap flag is active, force installation and exit
    if args.bootstrap:
        success = check_and_install_resources(interactive=False)
        sys.exit(0 if success else 1)
        
    # Otherwise, check / initialize interactively (or non-interactively if --no-prompt)
    if not check_and_install_resources(interactive=not args.no_prompt):
        print("❌ Cannot start: required resources are missing.")
        sys.exit(1)
        
    clock = ZeClock(color=args.color, animation_color=args.animation_color)
    asyncio.run(clock.run())


if __name__ == "__main__":
    main()
