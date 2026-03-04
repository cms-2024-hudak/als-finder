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
    
    # The USGS TNM API is unreliable for LiDAR point clouds and often returns 0 results for valid regions.
    # The modern, highly reliable approach is to use the Microsoft Planetary Computer STAC API
    # which hosts the complete USGS 3DEP LiDAR collection in COPC (Cloud Optimized Point Cloud) LAZ format.
    STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"

    def check_access(self) -> bool:
        """Check if the Planetary Computer STAC API is reachable."""
        try:
            requests.get("https://planetarycomputer.microsoft.com/api/stac/v1", timeout=5)
            return True
        except requests.RequestException:
            logger.warning("Microsoft Planetary Computer STAC API seems unreachable.")
            return False

    def search(self, roi: Polygon, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for USGS 3DEP LiDAR Point Cloud products using Planetary Computer STAC.
        """
        minx, miny, maxx, maxy = roi.bounds
        
        params = {
            "collections": "3dep-lidar-copc",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "limit": 100 # Adjust as needed for pagination
        }
        
        try:
            logger.info(f"Querying USGS 3DEP via STAC: {params}")
            response = requests.get(self.STAC_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            features = data.get('features', [])
            logger.info(f"Found {len(features)} items from USGS 3DEP.")
            
            results = []
            for item in features:
                # Planetary Computer assets include 'data' which points to the COPC.laz file
                assets = item.get('assets', {})
                data_asset = assets.get('data', {})
                url = data_asset.get('href')
                
                if not url:
                    continue
                    
                props = item.get('properties', {})
                
                results.append({
                    "provider": "USGS_STAC",
                    "dataset_id": item.get('id'),
                    "name": item.get('id'),
                    "url": url, 
                    "date": props.get('datetime'),
                    "size": None, # PC STAC might not always list exact bytes in summary
                    "preview": assets.get('thumbnail', {}).get('href'),
                    "metaUrl": item.get('links', [{}])[0].get('href'),
                    "bounds": props.get('proj:bbox', item.get('bbox')),
                    "geometry": item.get('geometry'), # Note: Full GeoJSON geometry for the tile
                    "point_count": props.get('pc:count'),
                    "point_density": props.get('pc:density'), # Often missing in USGS STAC, but good to check
                    "area_sqkm": None, # Often missing
                    "raw_metadata": item
                })
            return results

        except requests.RequestException as e:
            logger.error(f"Error searching USGS STAC: {e}")
            return []

    def download(self, tile_url: str, output_dir: Path, **kwargs) -> Path:
        """
        Download a specific .laz file from the USGS download URL.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract filename from URL (e.g., https://.../USGS_LPC_OR_...laz)
        filename = tile_url.split('/')[-1]
        out_path = output_dir / filename
        
        if out_path.exists():
            logger.info(f"File {out_path} already exists. Skipping download.")
            return out_path
            
        logger.info(f"Downloading USGS tile from {tile_url} to {out_path}")
        try:
            with requests.get(tile_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(out_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            logger.info(f"Successfully downloaded {filename}")
            return out_path
        except requests.RequestException as e:
            logger.error(f"Failed to download {tile_url}: {e}")
            if out_path.exists():
                out_path.unlink() # Clean up partial file
            raise
