from PIL import Image
import numpy as np
from typing import Tuple, Optional

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

def overlay_or_rgb(base: Image.Image, overlay: Image.Image, 
                   base_color: Tuple[int, int, int], 
                   overlay_color: Tuple[int, int, int]) -> Image.Image:
    """Combine grayscale images with different colors for each layer"""
    base_array = np.asarray(base)
    overlay_array = np.asarray(overlay)
    height, width = base_array.shape
    
    # Convert base to RGB with base_color
    rgb_array = np.zeros((height, width, 3), dtype=np.uint8)
    intensity_base = base_array / 255.0
    for i in range(3):
        rgb_array[:, :, i] = (base_color[i] * intensity_base).astype(np.uint8)
    
    # Apply overlay with overlay_color
    if hasattr(overlay, 'mask_data') and overlay.mask_data:
        mask_bytes = np.frombuffer(overlay.mask_data, dtype=np.uint8)
        y_indices, x_indices = np.mgrid[0:height, 0:width]
        byte_indices = (x_indices // 8) + (y_indices * overlay.mask_width_bytes)
        bit_positions = x_indices % 8
        valid_mask = byte_indices < len(mask_bytes)
        mask_vals = np.zeros((height, width), dtype=bool)
        mask_vals[valid_mask] = (mask_bytes[byte_indices[valid_mask]] >> bit_positions[valid_mask]) & 1
        
        # Where mask=0, apply overlay color
        intensity_overlay = overlay_array / 255.0
        for i in range(3):
            overlay_rgb = (overlay_color[i] * intensity_overlay).astype(np.uint8)
            rgb_array[:, :, i] = np.where(~mask_vals, overlay_rgb, rgb_array[:, :, i])
    else:
        # No mask: apply overlay color everywhere
        intensity_overlay = overlay_array / 255.0
        for i in range(3):
            rgb_array[:, :, i] = (overlay_color[i] * intensity_overlay).astype(np.uint8)
    
    return Image.fromarray(rgb_array, 'RGB')
