from PIL import Image

def overlay_or(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """Combine les deux images par OR logique pour effet DotClk"""
    base_bw = base.convert("1")
    over_bw = overlay.convert("1")
    merged = Image.new("1", base_bw.size)
    for y in range(base_bw.height):
        for x in range(base_bw.width):
            merged.putpixel((x, y),
                            255 if base_bw.getpixel((x, y)) or over_bw.getpixel((x, y)) else 0)
    return merged
