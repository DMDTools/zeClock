"""SCN file reader for zeClock"""


class ScnReader:
    """Reader for .scn animation files"""
    
    def __init__(self, filepath):
        self.filepath = filepath
        self.frames = []
    
    def load(self):
        """Load SCN file"""
        # TODO: Implement SCN file parsing
        pass
    
    def get_frame(self, index):
        """Get frame by index"""
        if 0 <= index < len(self.frames):
            return self.frames[index]
        return None
