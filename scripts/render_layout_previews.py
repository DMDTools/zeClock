#!/usr/bin/env python3
"""Render optimized weather plugin layout previews.

Output to /tmp/weather_layouts/ as 4x scaled PNGs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image
from zeclock.plugins.helpers import PluginHelpers
from zeclock.plugins.weather_icons import get_weather_icon_image

OUTPUT_DIR = Path("/tmp/weather_layouts")
OUTPUT_DIR.mkdir(exist_ok=True)

SCALE = 4
WIDTH, HEIGHT = 128, 32
RESOURCES = Path.home() / ".zeclock" / "resources"
helpers = PluginHelpers(WIDTH, HEIGHT, RESOURCES)

SUN_ICON = get_weather_icon_image(0)
CLOUD_ICON = get_weather_icon_image(3)
RAIN_ICON = get_weather_icon_image(61)


def save(img, name):
    scaled = img.resize((WIDTH * SCALE, HEIGHT * SCALE), Image.NEAREST)
    scaled.save(OUTPUT_DIR / f"{name}.png")
    print(f"  {name}.png")


def comp(base, overlay):
    return helpers.composite_frames(base, overlay)


def degree(frame, x, y, color):
    pixels = frame.load()
    for dx, dy in [(0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (2, 2)]:
        px, py = x + dx, y + dy
        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
            pixels[px, py] = color


# ============================================================
# PAGE 1: Current Conditions - OPTIMIZED
# ============================================================
print("Page 1: Current Conditions")


# 1A: Icon left, big temp right, description + city spread across bottom
def page1_a():
    frame = helpers.create_frame()
    frame.paste(SUN_ICON, (2, 1))
    # Temperature with degree - MENU font, right of icon
    t = helpers.render_text("23", x=20, y=1, color=(255, 128, 0), font_name="MENU")
    frame = comp(frame, t)
    nw = helpers.get_text_width("23", "MENU")
    degree(frame, 20 + nw + 1, 1, (255, 128, 0))
    t = helpers.render_text(
        "C", x=20 + nw + 5, y=1, color=(255, 128, 0), font_name="MENU"
    )
    frame = comp(frame, t)
    # Condition right-aligned area
    t = helpers.render_text(
        "Degage", x=70, y=3, color=(200, 200, 200), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    # City name bottom left, description bottom right
    t = helpers.render_text(
        "Grenoble", x=2, y=14, color=(128, 128, 255), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    # Horizontal separator line
    pixels = frame.load()
    for x in range(2, 126):
        pixels[x, 23] = (40, 40, 60)
    # Time at bottom right
    t = helpers.render_text(
        "14:32", x=95, y=25, color=(100, 100, 100), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    return frame


# 1B: Icon vertically centered left, temp BIG right, city+desc below
def page1_b():
    frame = helpers.create_frame()
    frame.paste(SUN_ICON, (4, 8))
    # Big temperature centered in right area
    t = helpers.render_text("23", x=28, y=2, color=(255, 128, 0), font_name="MENU")
    frame = comp(frame, t)
    nw = helpers.get_text_width("23", "MENU")
    degree(frame, 28 + nw + 1, 2, (255, 128, 0))
    t = helpers.render_text(
        "C", x=28 + nw + 5, y=2, color=(255, 128, 0), font_name="MENU"
    )
    frame = comp(frame, t)
    # Condition description
    t = helpers.render_text(
        "Degage", x=28, y=15, color=(200, 200, 200), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    # City right side
    t = helpers.render_text(
        "Grenoble", x=80, y=15, color=(128, 128, 255), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    # Thin line
    pixels = frame.load()
    for x in range(28, 126):
        pixels[x, 24] = (40, 40, 60)
    return frame


# 1C: Full width - icon left, temp+condition center, city right
def page1_c():
    frame = helpers.create_frame()
    frame.paste(SUN_ICON, (2, 3))
    # Temperature
    t = helpers.render_text("23", x=22, y=0, color=(255, 128, 0), font_name="MENU")
    frame = comp(frame, t)
    nw = helpers.get_text_width("23", "MENU")
    degree(frame, 22 + nw + 1, 0, (255, 128, 0))
    t = helpers.render_text(
        "C", x=22 + nw + 5, y=0, color=(255, 128, 0), font_name="MENU"
    )
    frame = comp(frame, t)
    # Condition
    t = helpers.render_text(
        "Degage", x=22, y=13, color=(200, 200, 200), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    # City bottom spanning full width
    t = helpers.render_text(
        "Grenoble", x=22, y=24, color=(128, 128, 255), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    # Right side: wind or extra info
    t = helpers.render_text(
        "5 km/h", x=85, y=4, color=(100, 180, 100), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    t = helpers.render_text(
        "65%", x=95, y=13, color=(100, 150, 200), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    return frame


save(page1_a(), "page1_A_balanced")
save(page1_b(), "page1_B_centered")
save(page1_c(), "page1_C_full_info")


# ============================================================
# PAGE 2: Tomorrow - OPTIMIZED
# ============================================================
print("Page 2: Tomorrow")


# 2A: Label top-left, icon center, temps right
def page2_a():
    frame = helpers.create_frame()
    t = helpers.render_text("DEMAIN", x=2, y=0, color=(255, 200, 0), font_name="MENU")
    frame = comp(frame, t)
    frame.paste(SUN_ICON, (2, 14))
    # High temp
    t = helpers.render_text("25", x=22, y=14, color=(255, 100, 50), font_name="MENU")
    frame = comp(frame, t)
    nw = helpers.get_text_width("25", "MENU")
    degree(frame, 22 + nw + 1, 14, (255, 100, 50))
    # Low temp
    t = helpers.render_text(
        "18C", x=22, y=26, color=(100, 150, 255), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    # Condition on right
    t = helpers.render_text(
        "Degage", x=70, y=4, color=(200, 200, 200), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    return frame


# 2B: Centered layout - icon big center, label top, temps flanking
def page2_b():
    frame = helpers.create_frame()
    # Label centered
    lw = helpers.get_text_width("DEMAIN", "MENU")
    t = helpers.render_text(
        "DEMAIN", x=(128 - lw) // 2, y=0, color=(255, 200, 0), font_name="MENU"
    )
    frame = comp(frame, t)
    # Icon centered
    frame.paste(SUN_ICON, (56, 13))
    # High left
    t = helpers.render_text("25C", x=15, y=18, color=(255, 100, 50), font_name="MENU")
    frame = comp(frame, t)
    # Low right
    t = helpers.render_text("18C", x=85, y=18, color=(100, 150, 255), font_name="MENU")
    frame = comp(frame, t)
    return frame


# 2C: Two-column - left: icon+temps, right: condition+details
def page2_c():
    frame = helpers.create_frame()
    t = helpers.render_text("DEMAIN", x=2, y=0, color=(255, 200, 0), font_name="MENU")
    frame = comp(frame, t)
    frame.paste(SUN_ICON, (2, 14))
    # Temps stacked next to icon
    t = helpers.render_text("25", x=21, y=13, color=(255, 100, 50), font_name="MENU")
    frame = comp(frame, t)
    nw = helpers.get_text_width("25", "MENU")
    degree(frame, 21 + nw + 1, 13, (255, 100, 50))
    t = helpers.render_text(
        "C", x=21 + nw + 5, y=13, color=(255, 100, 50), font_name="MENU"
    )
    frame = comp(frame, t)
    t = helpers.render_text(
        "18C", x=21, y=25, color=(100, 150, 255), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    # Right column: condition + extra
    t = helpers.render_text(
        "Degage", x=70, y=14, color=(200, 200, 200), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    t = helpers.render_text(
        "Vent: 12km/h", x=70, y=24, color=(100, 180, 100), font_name="SYSTEM"
    )
    frame = comp(frame, t)
    return frame


save(page2_a(), "page2_A_label_icon_temps")
save(page2_b(), "page2_B_symmetric")
save(page2_c(), "page2_C_two_column")


# ============================================================
# PAGE 3: 3-Day Outlook - OPTIMIZED
# ============================================================
print("Page 3: 3-Day Outlook")

icons = [SUN_ICON, CLOUD_ICON, RAIN_ICON]
days = ["Lun", "Mar", "Mer"]
temps = ["25", "22", "19"]


# 3A: Icon top, day name middle, temp bottom (current but tighter)
def page3_a():
    frame = helpers.create_frame()
    col_w = WIDTH // 3
    for i in range(3):
        col_x = i * col_w
        ix = col_x + (col_w - 16) // 2
        frame.paste(icons[i], (ix, 0))
        # Day name
        nw = helpers.get_text_width(days[i], "SYSTEM")
        t = helpers.render_text(
            days[i],
            x=col_x + (col_w - nw) // 2,
            y=17,
            color=(200, 200, 200),
            font_name="SYSTEM",
        )
        frame = comp(frame, t)
        # Temp
        tw = helpers.get_text_width(temps[i] + "C", "SYSTEM")
        t = helpers.render_text(
            temps[i] + "C",
            x=col_x + (col_w - tw) // 2,
            y=25,
            color=(255, 128, 0),
            font_name="SYSTEM",
        )
        frame = comp(frame, t)
    # Vertical separators
    pixels = frame.load()
    for y in range(0, 32):
        pixels[col_w, y] = (30, 30, 50)
        pixels[col_w * 2, y] = (30, 30, 50)
    return frame


# 3B: Day name on top, icon, temp bottom
def page3_b():
    frame = helpers.create_frame()
    col_w = WIDTH // 3
    for i in range(3):
        col_x = i * col_w
        # Day name top
        nw = helpers.get_text_width(days[i], "SYSTEM")
        t = helpers.render_text(
            days[i],
            x=col_x + (col_w - nw) // 2,
            y=0,
            color=(255, 200, 0),
            font_name="SYSTEM",
        )
        frame = comp(frame, t)
        # Icon middle
        ix = col_x + (col_w - 16) // 2
        frame.paste(icons[i], (ix, 8))
        # Temp bottom
        tw = helpers.get_text_width(temps[i] + "C", "SYSTEM")
        t = helpers.render_text(
            temps[i] + "C",
            x=col_x + (col_w - tw) // 2,
            y=25,
            color=(255, 128, 0),
            font_name="SYSTEM",
        )
        frame = comp(frame, t)
    return frame


# 3C: Day name top in MENU, icon below, no temp (cleaner)
def page3_c():
    frame = helpers.create_frame()
    col_w = WIDTH // 3
    for i in range(3):
        col_x = i * col_w
        # Day name top - MENU font for readability
        nw = helpers.get_text_width(days[i].upper(), "MENU")
        t = helpers.render_text(
            days[i].upper(),
            x=col_x + (col_w - nw) // 2,
            y=0,
            color=(255, 200, 0),
            font_name="MENU",
        )
        frame = comp(frame, t)
        # Icon below
        ix = col_x + (col_w - 16) // 2
        frame.paste(icons[i], (ix, 13))
        # Small temp at very bottom
        tw = helpers.get_text_width(temps[i] + "C", "SYSTEM")
        # Don't show temp - just icon + day for clean look
    return frame


save(page3_a(), "page3_A_separators")
save(page3_b(), "page3_B_day_top")
save(page3_c(), "page3_C_clean")

print(f"\nAll saved to {OUTPUT_DIR}/")
print("View: xdg-open /tmp/weather_layouts/")
