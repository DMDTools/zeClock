#!/usr/bin/env python3
"""Debug script for analyzing .scn scene rendering issues.

Usage:
    uv run python scripts/debug_scene.py RD0673.scn [--send]

Loads the scene, dumps frame metadata, saves individual frames as PNG,
and optionally sends them to the virtual DMD for live visualization.
"""

import argparse
import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from zeclock.readers.scn_reader import Scene, load_scene
from zeclock.overlay import overlay_or_rgb, colorize_grayscale
from zeclock.colors import COLOR_MAP


def dump_scene_info(scene: Scene) -> None:
    """Print all metadata about the scene."""
    print(f"\n{'='*60}")
    print(f"Scene: {scene.path.name}")
    print(f"{'='*60}")
    print(f"  Dimensions: {scene.width}x{scene.height}")
    print(f"  Frame count: {scene.frame_count}")
    print(f"  Actual frames loaded: {len(scene.frames)}")
    print(f"  Frame delay (ms): {scene.frame_delay_ms}")
    print(
        f"  FPS: {1000.0 / scene.frame_delay_ms if scene.frame_delay_ms > 0 else 'N/A':.1f}"
    )
    print(f"\n  Storyboard:")
    print(f"    first_frame_delay: {scene.first_frame_delay}")
    print(f"    first_frame_layer: {scene.first_frame_layer}")
    print(f"    first_blank: {scene.first_blank}")
    print(f"    frame_delay_ms: {scene.frame_delay_ms}")
    print(f"    frame_layer: {scene.frame_layer}")
    print(f"    last_frame_delay: {scene.last_frame_delay}")
    print(f"    last_frame_layer: {scene.last_frame_layer}")
    print(f"    last_blank: {scene.last_blank}")
    print(f"    clock_style: {scene.clock_style}")
    print(f"    custom_x: {scene.custom_x}")
    print(f"    custom_y: {scene.custom_y}")
    print()


def analyze_frames(scene: Scene, output_dir: Path) -> None:
    """Analyze each frame and save as PNG."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Saving frames to: {output_dir}/")
    print(
        f"  {'Frame':<8} {'Size':<12} {'Mode':<6} {'HasMask':<9} {'MinPx':<6} {'MaxPx':<6} {'MeanPx':<8}"
    )
    print(f"  {'-'*55}")

    for i, frame in enumerate(scene.frames):
        has_mask = hasattr(frame, "mask_data") and frame.mask_data is not None
        stats = frame.getextrema()
        mean_val = sum(frame.getdata()) / (frame.size[0] * frame.size[1])

        # Print info for first few frames and last few
        if i < 5 or i >= len(scene.frames) - 3:
            print(
                f"  {i:<8} {frame.size[0]}x{frame.size[1]:<6} {frame.mode:<6} "
                f"{'Yes' if has_mask else 'No':<9} {stats[0]:<6} {stats[1]:<6} {mean_val:<8.1f}"
            )
        elif i == 5:
            print(f"  ... ({len(scene.frames) - 8} more frames) ...")

        # Save every Nth frame + first and last
        if (
            i < 3
            or i >= len(scene.frames) - 2
            or i % max(1, len(scene.frames) // 10) == 0
        ):
            # Save raw grayscale
            frame.save(output_dir / f"frame_{i:04d}_raw.png")

            # Save colorized version (orange)
            color = COLOR_MAP["orange"]
            colorized = colorize_grayscale(frame, color)
            colorized.save(output_dir / f"frame_{i:04d}_color.png")

    print(f"\n  Saved sample frames to {output_dir}/")


def render_with_overlay(scene: Scene, output_dir: Path) -> None:
    """Render frames with clock overlay like the plugin does."""
    from zeclock.readers import load_font
    from zeclock.resources.paths import get_fonts_dir

    fonts_dir = get_fonts_dir()
    font_path = fonts_dir / "STANDARD.fnt"

    if not font_path.exists():
        print(f"  ⚠️  Font not found at {font_path}, skipping overlay render")
        return

    font = load_font(font_path)
    display_time = "12:34"
    color = COLOR_MAP["orange"]
    animation_color = COLOR_MAP["orange"]

    overlay_dir = output_dir / "overlay"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"\n  Rendering with clock overlay (clock_style={scene.clock_style}, "
        f"frame_layer={scene.frame_layer})..."
    )

    for i, animation_frame in enumerate(scene.frames):
        if (
            i < 3
            or i >= len(scene.frames) - 2
            or i % max(1, len(scene.frames) // 10) == 0
        ):
            # Render clock
            if scene.clock_style == 1:
                # Custom position
                text_width = font.get_text_width(display_time)
                text_height = font.char_height
                x_pos = max(
                    0, min(scene.custom_x - (text_width // 2), scene.width - text_width)
                )
                y_pos = max(
                    0,
                    min(
                        scene.custom_y - (text_height // 2), scene.height - text_height
                    ),
                )
                clock_frame = Image.new("L", (scene.width, scene.height), 0)
                text_img = font.render_text(display_time, text_width, text_height)
                clock_frame.paste(text_img, (x_pos, y_pos))
            else:
                clock_frame = font.render_text(display_time, scene.width, scene.height)

            # Merge with DotBlt
            if scene.frame_layer == 1:
                merged = overlay_or_rgb(
                    animation_frame, clock_frame, animation_color, color
                )
            else:
                merged = overlay_or_rgb(
                    clock_frame, animation_frame, color, animation_color
                )

            merged.save(overlay_dir / f"frame_{i:04d}_merged.png")

    print(f"  Saved overlay frames to {overlay_dir}/")


def send_to_virtual_dmd(
    scene: Scene, host: str = "localhost", port: int = 6789
) -> None:
    """Send frames to the virtual DMD server for live preview."""
    color = COLOR_MAP["orange"]

    print(f"\n  Sending frames to virtual DMD at {host}:{port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
    except ConnectionRefusedError:
        print(f"  ❌ Cannot connect to virtual DMD at {host}:{port}")
        print(f"     Start it with: uv run python scripts/virtual-dmd.py 6789")
        return

    try:
        for i, frame in enumerate(scene.frames):
            # Colorize to RGB
            colorized = colorize_grayscale(frame, color)
            width, height = colorized.size

            # Convert to RGB24 bytes
            rgb_data = colorized.tobytes()

            # DMDStream header
            header = b"DMDStream\x00"
            header += struct.pack(">B", 0)  # padding
            header += struct.pack(">I", 2)  # mode=2 (RGB24)
            header += struct.pack(">H", width)
            header += struct.pack(">H", height)
            header += struct.pack(">H", 0)  # padding
            header += struct.pack(">I", len(rgb_data))

            sock.sendall(header + rgb_data)

            # Respect frame timing
            delay = scene.frame_delay_ms / 1000.0
            time.sleep(delay)

            if i % 20 == 0:
                print(f"    Frame {i}/{len(scene.frames)}", end="\r")

        print(f"    Done! Sent {len(scene.frames)} frames.          ")
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Debug .scn scene rendering")
    parser.add_argument("scene", help="Scene filename (e.g., RD0673.scn) or full path")
    parser.add_argument(
        "--send", action="store_true", help="Send frames to virtual DMD"
    )
    parser.add_argument(
        "--no-overlay", action="store_true", help="Skip overlay rendering"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output directory for frame captures",
    )
    parser.add_argument("--host", default="localhost", help="Virtual DMD host")
    parser.add_argument("--port", type=int, default=6789, help="Virtual DMD port")
    args = parser.parse_args()

    # Resolve scene path
    scene_path = Path(args.scene)
    if not scene_path.exists():
        # Try in animations directory
        from zeclock.paths import get_resources_dir

        animations_dir = get_resources_dir() / "animations"
        scene_path = animations_dir / args.scene
        if not scene_path.exists():
            # Try recursive search
            matches = list(animations_dir.glob(f"**/{args.scene}"))
            if matches:
                scene_path = matches[0]
            else:
                print(f"❌ Scene not found: {args.scene}")
                print(f"   Searched in: {animations_dir}")
                sys.exit(1)

    # Load scene
    print(f"Loading scene: {scene_path}")
    scene = load_scene(scene_path, 128, 32)

    # Dump info
    dump_scene_info(scene)

    # Output directory
    output_dir = (
        Path(args.output)
        if args.output
        else Path(f"/tmp/zeclock_debug_{scene_path.stem}")
    )

    # Analyze frames
    analyze_frames(scene, output_dir)

    # Render with overlay
    if not args.no_overlay:
        render_with_overlay(scene, output_dir)

    # Send to virtual DMD
    if args.send:
        send_to_virtual_dmd(scene, args.host, args.port)

    print(f"\n✅ Debug complete. Frames saved to: {output_dir}")


if __name__ == "__main__":
    main()
