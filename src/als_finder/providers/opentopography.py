import requests
import logging
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon
from pathlib import Path
import os
from .base import BaseProvider

logger = logging.getLogger(__name__)

class OpenTopographyProvider(BaseProvider):
    """
    Provider implementation for OpenTopography.
    Docs: https://portal.opentopography.org/apidocs/
    """
    
    BASE_URL = "https://portal.opentopography.org/API"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENTOPOGRAPHY_API_KEY")
        if not self.api_key:
            logger.warning("No OpenTopography API key found. Some functionalities might be limited.")

    def check_access(self) -> bool:
        """Check if API key is present and valid by hitting a lightweight endpoint."""
        if not self.api_key:
            logger.error("OpenTopography API Key is missing. Please set OPENTOPOGRAPHY_API_KEY.")
            return False
            
        # Verify connectivity/key with a lightweight call (e.g. searching for a tiny area or checking user info if possible)
        # OT doesn't have a dedicated 'whoami' endpoint, so we might just assume True if Key exists 
        # or try a minimal valid search.
        try:
            # Minimal search check
            response = requests.get(f"{self.BASE_URL}/otCatalog", params={"productFormat": "PointCloud", "minx": -120, "miny": 38, "maxx": -119.9, "maxy": 38.1, "detail": "false"}, timeout=10)
            if response.status_code == 401:
                logger.error("OpenTopography API Key is invalid.")
                return False
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to connect to OpenTopography: {e}")
            return False

    def search(self, roi: Polygon, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for global datasets available via OpenTopography.
        
        Note: OT has different endpoints for 'GlobalData' (SRTM, ALOS) vs High Res.
        We primarily target High Res point cloud data if possible, but their API
        for searching specific point cloud datasets via BBox is 'otCatalog'.
        """
        minx, miny, maxx, maxy = roi.bounds
        
        # Using the otCatalog API to find datasets
        # https://portal.opentopography.org/API/otCatalog?productFormat=PointCloud&minx=...
        
        params = {
            "productFormat": "PointCloud",
            "minx": minx,
            "miny": miny,
            "maxx": maxx,
            "maxy": maxy,
            "detail": "true",
            "outputFormat": "json"
        }
        
        try:
            response = requests.get(f"{self.BASE_URL}/otCatalog", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # The structure is usually {'Datasets': [...]}
            datasets = data.get('Datasets', [])
            logger.info(f"Found {len(datasets)} datasets from OpenTopography.")
            
            results = []
            for ds in datasets:
                # Normalize metadata
                results.append({
                    "provider": "OpenTopography",
                    "dataset_id": ds.get('opentopoID'),
                    "name": ds.get('title'),
                    "url": ds.get('uri'),
                    "bounds": ds.get('coverage'),
                    "year": ds.get('year'),
                    # Store raw for full context
                    "raw_metadata": ds
                })
            return results

        except requests.RequestException as e:
            logger.error(f"Error searching OpenTopography: {e}")
            return []

    def download(self, dataset_id: str, output_dir: Path, **kwargs) -> Path:
        """
        Download handling for OT is complex because it involves job submission 
        for point clouds.
        
        For this initial version, we might need to point users to the URL 
        or implement the job submission flow (GlobalData is easier).
        
        Ref: https://portal.opentopography.org/API/globalData
        Ref: https://portal.opentopography.org/API/usgsDem
        
        Implementing true Point Cloud download via API requires:
        1. /lidar processing job submission
        2. Polling for completion
        3. Downloading result
        """
        logger.warning("Direct point cloud download processing not yet fully implemented.")
        # Placeholder
        return output_dir
