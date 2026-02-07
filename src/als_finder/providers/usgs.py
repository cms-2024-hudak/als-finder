import logging
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon
from pathlib import Path
import requests
import json
from .base import BaseProvider

logger = logging.getLogger(__name__)

class USGSProvider(BaseProvider):
    """
    Provider for USGS 3DEP data via AWS Public Datasets.
    Uses the underlying Entwine index / USGS API to find tiles.
    """
    
    def check_access(self) -> bool:
        """USGS 3DEP is public, but we can check if the TNM API is reachable."""
        try:
            requests.get(self.TNM_URL, timeout=5)
            return True
        except requests.RequestException:
            logger.warning("USGS TNM API seems unreachable.")
            return False
    
    # This endpoint searches the Entwine index for USGS 3DEP data
    # Reference: https://usgs.entwine.io/
    # Note: Direct spatial search on S3 is hard. We often use an index service.
    # A common way is to use the USGS National Map API or Entwine's index if available.
    # For this implementation, we will use the highly effective 'usgslidar' package approach
    # or a public STAC API if robust.
    # To keep it simple and dependency-light, we'll use the National Map API for search
    # or the entwine boundaries if possible.
    
    # Actually, a better approach for 3DEP without heavy deps is the USGS TNM Access API.
    TNM_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"

    def search(self, roi: Polygon, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for USGS 3DEP LiDAR Point Cloud products (LPC).
        """
        minx, miny, maxx, maxy = roi.bounds
        
        params = {
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "prodFormats": "LAZ,LAS",
            "datasets": "Lidar Point Cloud (LPC)", 
            # "max": 10  # Limit for testing
        }
        
        try:
            logger.info(f"Querying USGS TNM: {params}")
            response = requests.get(self.TNM_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # TNM returns a list of items
            items = data.get('items', [])
            logger.info(f"Found {len(items)} items from USGS.")
            
            results = []
            for item in items:
                # Filter strictly if needed, TNM bbox search is sometimes loose
                results.append({
                    "provider": "USGS",
                    "dataset_id": item.get('id'),
                    "name": item.get('title'),
                    "url": item.get('downloadURL'), # Direct download link for LAZ
                    "date": item.get('publicationDate'),
                    "size": item.get('sizeInBytes'),
                    "preview": item.get('previewGraphicURL'),
                    "metaUrl": item.get('metaUrl'),
                    "raw_metadata": item
                })
            return results

        except requests.RequestException as e:
            logger.error(f"Error searching USGS: {e}")
            return []

    def download(self, dataset_id: str, output_dir: Path, **kwargs) -> Path:
        """
        Download a file from USGS (usually direct URL).
        """
        # In a real implementation, we'd lookup the URL from the search result 
        # or require the URL to be passed.
        # For simplistic interface, let's assume the 'dataset_id' might be the URL or we re-fetch.
        
        # NOTE: Proper design would pass the full metadata object or URL to download.
        # Here we just log it as a placeholder.
        logger.info(f"Downloading {dataset_id} to {output_dir}")
        return output_dir
