from PIL import Image
import numpy as np

def overlay_or(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """Combine images using DotClk DotBlt logic: base first, then overlay with mask"""
    base_array = np.array(base.convert("L") if base.mode != "L" else base)
    overlay_array = np.array(overlay.convert("L") if overlay.mode != "L" else overlay)
    
    # Start with base (like DotClk frame)
    merged_array = base_array.copy()
    
    # Check if overlay has mask data
    if hasattr(overlay, 'mask_data') and overlay.mask_data:
        # Use DotClk DotBlt logic with correct bit ordering
        height, width = overlay_array.shape
        mask_bytes = np.frombuffer(overlay.mask_data, dtype=np.uint8)
        
        # Apply DotBlt logic: mask=0 means use overlay, mask=1 means keep base
        for y in range(height):
            for x in range(width):
                byte_idx = (x // 8) + (y * overlay.mask_width_bytes)
                if byte_idx < len(mask_bytes):
                    bit_pos = x % 8
                    mask_val = bool(mask_bytes[byte_idx] & (1 << bit_pos))
                    if mask_val:  # mask=1: keep base pixel
                        pass  # Already copied base
                    else:  # mask=0: use overlay pixel (including black!)
                        merged_array[y, x] = overlay_array[y, x]
    else:
        # No mask: fonts should overlay completely (including black pixels)
        # For fonts, treat all pixels as opaque - use overlay where it exists
        merged_array = overlay_array
    
    return Image.fromarray(merged_array, 'L')
