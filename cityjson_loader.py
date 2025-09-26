import json
import os

class CityJSONLoader:
    """Loads the CityJSON file and calculates coordinates from the metadata."""
    
    @staticmethod
    def load_cityjson(file_path):
        "Loads the CityJSON file and calculates the center point from the extent."
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(file_path, 'r') as f:
            cm = json.load(f)
        
        # Extent ve CRS kontrolü
        extent = cm.get('metadata', {}).get('geographicalExtent', None)
        if not extent or len(extent) != 6:
            raise ValueError("geographicalExtent is missing or invalid in the metadata.")
        
        crs = cm.get('metadata', {}).get('referenceSystem', None)
        if not crs:
            raise ValueError("referenceSystem (CRS) is missing in the metadata.")
        
        min_x, min_y, _, max_x, max_y, _ = extent
        x_mid = (min_x + max_x) / 2
        y_mid = (min_y + max_y) / 2
        return cm, x_mid, y_mid, crs