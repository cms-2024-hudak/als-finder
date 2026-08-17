import logging
import geopandas as gpd
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon
from pathlib import Path
from .base import BaseProvider
import requests

logger = logging.getLogger(__name__)

class USGSProvider(BaseProvider):
    """
    Provider for USGS 3DEP data via AWS Public Datasets (EPT format).
    Reads the authoritative US boundary geometry file locally representing true Scale 2 Acquisitions.
    """
    
    REGISTRY_URL = "https://raw.githubusercontent.com/hobu/usgs-lidar/master/boundaries/resources.geojson"
    CACHE_DIR = Path.home() / ".cache" / "als_finder"
    CACHE_FILE = CACHE_DIR / "usgs_resources.geojson"

    def check_access(self) -> bool:
        """Check if Github registry is reachable or cached."""
        if self.CACHE_FILE.exists() and self.CACHE_FILE.stat().st_size > 10000:
            return True
        try:
            r = requests.get(self.REGISTRY_URL, headers={"User-Agent": "als-finder/1.1"}, stream=True, timeout=10)
            return r.status_code == 200
        except requests.RequestException:
            if self.CACHE_FILE.exists():
                return True
            logger.warning("AWS USGS Entwine boundary registry unreachable.")
            return False

    def search(self, roi: Polygon, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for USGS 3DEP LiDAR Point Cloud products intersecting the ROI.
        """
        try:
            if not (self.CACHE_FILE.exists() and self.CACHE_FILE.stat().st_size > 10000):
                logger.info("Downloading Hobu USGS 3DEP Global AWS Index...")
                self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                r = requests.get(self.REGISTRY_URL, headers={"User-Agent": "als-finder/1.1"}, timeout=30)
                r.raise_for_status()
                with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                    f.write(r.text)

            gdf = gpd.read_file(self.CACHE_FILE)
            logger.info(f"Loaded {len(gdf)} entire USGS acquisitions natively.")
            
            if roi:
                roi_gdf = gpd.GeoDataFrame(geometry=[roi], crs="EPSG:4326")
                
                if gdf.crs is None:
                    gdf.set_crs("EPSG:4326", inplace=True)
                elif gdf.crs != roi_gdf.crs:
                    gdf = gdf.to_crs(roi_gdf.crs)
                    
                logger.info("Intersecting spatial boundaries natively...")
                intersecting = gdf[gdf.intersects(roi)]
                logger.info(f"Found {len(intersecting)} USGS datasets spanning the ROI.")
            else:
                logger.info("No spatial constraint natively mapped. Evaluating the entire mathematical footprint.")
                intersecting = gdf
            
            import re
            results = []
            for idx, row in intersecting.iterrows():
                name = str(row.get('name', 'Unknown'))
                geom = row.geometry
                bounds = geom.bounds if geom else None
                geom_dict = geom.__geo_interface__ if geom else None
                
                # Derive year structurally via regex
                year_match = re.search(r'_?(199\d|20[0-2]\d)_?', name)
                extracted_date = year_match.group(1) if year_match else None
                
                # Stringify row for raw generic tracking
                raw_dict = {}
                for k in row.index:
                    if k != 'geometry':
                        raw_dict[str(k)] = str(row[k])
                        
                clean_raw = self.sanitize_metadata(raw_dict)
                results.append({
                    "provider": "USGS_EPT",
                    "dataset_id": name,
                    "name": name,
                    "description": f"USGS 3DEP EPT Dataset: {name}",
                    "url": f"https://s3-us-west-2.amazonaws.com/usgs-lidar-public/{name}/ept.json", 
                    "date": extracted_date,
                    "size": None,
                    "preview": None,
                    "metaUrl": self.REGISTRY_URL,
                    "srs": "EPSG:4326",
                    "bounds": bounds,
                    "geometry": geom_dict, 
                    "point_count": row.get('count'),
                    "point_density": None,
                    "area_sqkm": None,
                    "raw_metadata": clean_raw,
                    "additional_metadata": clean_raw
                })
            return results

        except Exception as e:
            logger.error(f"Error searching USGS AWS EPT registry: {e}")
            return []

    def download(self, tile_url: str, output_dir: Path, **kwargs) -> Path:
        """
        Scale 2 USGS data streams via EPT (Entwine Point Tiles) structurally natively.
        """
        logger.warning(f"Extracted USGS datasets are Entwine Point Tile (EPT) URLs ({tile_url}).")
        logger.warning("To extract natively, use PDAL targeting the ept.json payload directly rather than standard wget endpoints.")
        return output_dir

    def get_pdal_reader(self, urls: List[str], buffered_poly: Polygon, poly_crs: str = "EPSG:3857", resolution: Optional[float] = 2.0) -> List[Dict[str, Any]]:
        # USGS EPT reader expects bounds in Web Mercator (EPSG:3857)
        if poly_crs and poly_crs.upper() != "EPSG:3857":
            gdf = gpd.GeoDataFrame(geometry=[buffered_poly], crs=poly_crs)
            gdf_3857 = gdf.to_crs("EPSG:3857")
            target_poly = gdf_3857.geometry.iloc[0]
        else:
            target_poly = buffered_poly

        b_minx, b_miny, b_maxx, b_maxy = target_poly.bounds
        bounds_str = f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])"
        reader_stage = {
            "type": "readers.ept",
            "filename": urls[0],
            "bounds": bounds_str
        }
        if resolution:
            reader_stage["resolution"] = float(resolution)
        return [reader_stage]
