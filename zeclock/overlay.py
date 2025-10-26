from PIL import Image
import numpy as np

def overlay_or(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """Combine two 4-bit grayscale images like DotClk DotBlt (optimized)"""
    # Ensure both images are grayscale
    base_gray = base.convert("L") if base.mode != "L" else base
    overlay_gray = overlay.convert("L") if overlay.mode != "L" else overlay
    
    # Convert to numpy arrays for fast operations
    base_array = np.array(base_gray)
    overlay_array = np.array(overlay_gray)
    
    # DotClk behavior: overlay pixel takes precedence if non-zero
    # Use numpy where for vectorized operation
    merged_array = np.where(overlay_array > 0, overlay_array, base_array)
    
    return Image.fromarray(merged_array, 'L')
