from PIL import Image
import numpy as np

def overlay_or(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """Combine images using overlay logic: base first, then overlay with mask"""
    base_array = np.asarray(base)
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
        
        # Apply mask: where mask=1 preserve base, where mask=0 use overlay (preserving all values)
        return Image.fromarray(np.where(mask_vals, base_array, overlay_array), 'L')
    else:
        # No mask: use overlay where it's non-zero, otherwise base
        return Image.fromarray(np.where(overlay_array > 0, overlay_array, base_array), 'L')
