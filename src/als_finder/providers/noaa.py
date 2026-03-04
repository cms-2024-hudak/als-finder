import logging
import os
import json
import concurrent.futures
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon, box, shape
from pathlib import Path
import geopandas as gpd
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from .base import BaseProvider

logger = logging.getLogger(__name__)

class NOAAProvider(BaseProvider):
    """
    Provider for NOAA Digital Coast LiDAR via AWS Open Data STAC.
    Since NOAA does not currently provide a dynamic STAC spatial search API,
    this provider builds a swift local spatial index from the ~950 static STAC items.
    """
    
    CATALOG_URL = "https://noaa-nos-coastal-lidar-pds.s3.us-east-1.amazonaws.com/entwine/stac/catalog.json"
    INDEX_FILE = Path.home() / ".cache" / "als-finder" / "noaa_stac_bounds.geojson"

    def __init__(self):
        self.INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Configure a robust session for fetching Many JSONs
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[ 500, 502, 503, 504 ])
        self.session.mount('https://', HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20))

    def check_access(self) -> bool:
        """Check if the NOAA AWS STAC catalog is reachable."""
        try:
            self.session.head(self.CATALOG_URL, timeout=5)
            return True
        except requests.RequestException:
            logger.warning("NOAA AWS STAC catalog seems unreachable.")
            return False

    def _fetch_json(self, url: str) -> Optional[Dict]:
        """Helper to fetch a JSON file using robust session."""
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return None

    def _build_index(self):
        """
        Downloads all ~950 STAC items concurrently and builds a GeoJSON spatial index.
        """
        logger.info(f"Building local NOAA STAC spatial index at {self.INDEX_FILE}...")
        logger.info("Fetching STAC metadata for ~950 datasets. This normally takes ~15 seconds and only happens once.")
        
        catalog = self._fetch_json(self.CATALOG_URL)
        if not catalog:
            logger.error("Failed to load NOAA STAC Catalog.")
            return

        # Find all item links
        links = [l['href'] for l in catalog.get('links', []) if l.get('rel') == 'item']
        base_url = self.CATALOG_URL.rsplit('/', 1)[0]
        item_urls = [base_url + "/" + link.lstrip('./') for link in links]
        
        features = []
        logger.info(f"Fetching {len(item_urls)} STAC definitions concurrently...")
        
        # Reduced max workers to 15 to avoid overwhelming the S3 rate limit or local file descriptors
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            future_to_url = {executor.submit(self._fetch_json, url): url for url in item_urls}
            
            # Use a simple counter to log progress
            completed = 0
            for future in concurrent.futures.as_completed(future_to_url):
                completed += 1
                if completed % 200 == 0:
                    logger.info(f" ... fetched {completed} / {len(item_urls)} items")
                    
                item = future.result()
                if not item:
                    continue
                
                # Extract bbox or geometry
                bbox = item.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                    
                # Extract data URL
                assets = item.get("assets", {})
                data_url = None
                for asset_key, asset in assets.items():
                    if "laz" in asset_key.lower() or "data" in asset_key.lower():
                         data_url = asset.get("href")
                         break
                
                if not data_url:
                     if assets:
                         data_url = list(assets.values())[0].get("href")
                     else:
                         continue

                geom = box(*bbox)
                
                feature = {
                    "type": "Feature",
                    "geometry": geom.__geo_interface__,
                    "properties": {
                        "id": item.get("id"),
                        "title": item.get("title", item.get("id")),
                        "url": data_url,
                        "datetime": item.get("properties", {}).get("datetime", ""),
                        "stac_url": future_to_url[future]
                    }
                }
                features.append(feature)

        # Save to GeoJSON
        geojson_data = {
            "type": "FeatureCollection",
            "features": features
        }
        
        with open(self.INDEX_FILE, 'w') as f:
            json.dump(geojson_data, f)
            
        logger.info(f"Successfully cached {len(features)} NOAA datasets.")

    def search(self, roi: Polygon, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for NOAA LiDAR data by querying the local spatial index.
        """
        if not self.INDEX_FILE.exists():
            self._build_index()

        if not self.INDEX_FILE.exists():
            logger.error("NOAA STAC index could not be built.")
            return []

        # Load GeoJSON into GeoPandas
        try:
            gdf = gpd.read_file(self.INDEX_FILE)
        except Exception as e:
            logger.error(f"Failed to read NOAA index {self.INDEX_FILE}: {e}")
            return []

        # WGS84 coordinates 
        if gdf.crs is None:
             gdf.set_crs(epsg=4326, inplace=True)

        # Create a GeoDataFrame for the ROI
        roi_gdf = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[roi])

        # Perform spatial intersection
        intersecting = gpd.sjoin(gdf, roi_gdf, how="inner", predicate="intersects")
        
        logger.info(f"Found {len(intersecting)} items from NOAA.")
        
        results = []
        for idx, row in intersecting.iterrows():
            results.append({
                "provider": "NOAA_STAC",
                "dataset_id": row.get("id"),
                "name": row.get("title"),
                "url": row.get("url"), 
                "date": row.get("datetime"),
                "size": None, 
                "preview": None,
                "metaUrl": row.get("stac_url"),
                "bounds": row.geometry.bounds if getattr(row, 'geometry', None) else None,
                "geometry": row.geometry.__geo_interface__ if getattr(row, 'geometry', None) else None,
                "point_count": None,
                "point_density": None,
                "area_sqkm": None,
                "raw_metadata": {"id": row.get("id"), "title": row.get("title")}
            })
            
        return results

    def download(self, tile_url: str, output_dir: Path, **kwargs) -> Path:
        """
        NOAA provides data in various forms (sometimes LAZ directly, sometimes Entwine). 
        For now we will just download the target file directly if it's a file URL.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = tile_url.split('/')[-1]
        out_path = output_dir / filename
        
        if out_path.exists():
            logger.info(f"File {out_path} already exists. Skipping download.")
            return out_path
            
        logger.info(f"Downloading NOAA dataset from {tile_url} to {out_path}")
        try:
            with requests.get(tile_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(out_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            logger.info(f"Successfully downloaded NOAA dataset {filename}")
            return out_path
        except requests.RequestException as e:
            logger.error(f"Failed to download NOAA data {tile_url}: {e}")
            if out_path.exists():
                out_path.unlink()
            raise
