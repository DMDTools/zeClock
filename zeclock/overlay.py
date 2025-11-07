from PIL import Image
import numpy as np

def overlay_or(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """Combine images using DotClk DotBlt logic: mask=1 preserves dest, mask=0 copies source"""
    base_array = np.asarray(base).copy()
    overlay_array = np.asarray(overlay)
    
    # Check if overlay has mask data
    if hasattr(overlay, 'mask_data') and overlay.mask_data:
        # Vectorized mask processing
        height, width = overlay_array.shape
        mask_bytes = np.frombuffer(overlay.mask_data, dtype=np.uint8)
        
        # Create mask array using vectorized operations
        y_indices, x_indices = np.mgrid[0:height, 0:width]
        byte_indices = (x_indices // 8) + (y_indices * overlay.mask_width_bytes)
        bit_positions = x_indices % 8
        
        # Vectorized mask extraction
        valid_mask = byte_indices < len(mask_bytes)
        mask_vals = np.zeros((height, width), dtype=bool)
        mask_vals[valid_mask] = (mask_bytes[byte_indices[valid_mask]] >> bit_positions[valid_mask]) & 1
        
        # DotClk DotBlt logic: 
        # - mask=0: copy overlay (even if 0)
        # - mask=1: keep base
        result = np.where(~mask_vals, overlay_array, base_array)
        return Image.fromarray(result, 'L')
    else:
        # No mask: treat as fully opaque (mask=0 everywhere)
        # Copy all overlay pixels, even zeros
        return Image.fromarray(overlay_array, 'L')
