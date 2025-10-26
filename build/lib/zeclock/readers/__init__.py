"""
Readers pour les formats DotClk
"""
from .fnt_reader import DotClkFont, load_font
from .scn_reader import DotClkScene, load_scene

__all__ = ['DotClkFont', 'load_font', 'DotClkScene', 'load_scene']
