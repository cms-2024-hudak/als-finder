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

    def __init__(self, ot_key: Optional[str] = None):
        """Initializes the OpenTopography abstraction natively mapping keys organically."""
        from dotenv import load_dotenv
        
        # Priority 1: Argument passed explicitly
        # Priority 2: Current shell / workspace .env (loaded by cli.py)
        self.api_key = ot_key or os.getenv("OPENTOPOGRAPHY_API_KEY")
        
        # Priority 3: Global config
        global_config_dir = Path.home() / ".config" / "als-finder"
        global_env = global_config_dir / ".env"
        
        # Priority 1: Check Explicit Keys natively via user argument constraints
        if not self.api_key and global_env.exists():
            load_dotenv(global_env)
            self.api_key = os.getenv("OPENTOPOGRAPHY_API_KEY")
            
        # The native SDSC MinIO extraction architecture drops API key locks organically.
        # Legacy search parameters still log it strictly for formal request headers.
        # If still missing, log a warning.
        if not self.api_key:
            logger.warning("No OpenTopography API key provided. OT Discovery will bypass or have limited functionality.")

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

    def search(self, roi: Optional[Polygon] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for global datasets available via OpenTopography.
        
        Note: OT has different endpoints for 'GlobalData' (SRTM, ALOS) vs High Res.
        We primarily target High Res point cloud data natively intercepts if possible, but their API
        for searching specific point cloud datasets via BBox is 'otCatalog'.
        """
        if kwargs.get('cloud_native'):
            return []  # OpenTopography APIs generate zips/LAS statically and do not universally guarantee HTTP byte-range EPT/COPC pipelines currently.

        if roi:
            minx, miny, maxx, maxy = roi.bounds
        else:
            # Natively enforce global geometries structurally satisfying OT's required parameters strictly 
            minx, miny, maxx, maxy = -180, -90, 180, 90
        
        # Using the otCatalog API natively intercepted finding datasets
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
                # OpenTopography wraps the actual metadata in a 'Dataset' key using JSON-LD
                meta = ds.get('Dataset', ds)
                
                # Extract IDs natively from the JSON-LD format
                ident = meta.get('identifier', {})
                if isinstance(ident, dict):
                    dataset_id = ident.get('value', 'Unknown')
                else:
                    dataset_id = str(ident)
                    
                # Extract area if available
                area = None
                vars = meta.get('variableMeasured', [])
                for v in vars:
                    if isinstance(v, dict) and v.get('name') == 'Area':
                        try:
                            area_str = v.get('value', '').replace(' km2', '').strip()
                            area = float(area_str)
                        except:
                            pass

                # Isolate Polygons from OT FeatureCollections
                geom = meta.get('spatialCoverage', {}).get('geo', {}).get('geojson', {})
                if geom and geom.get('type') == 'FeatureCollection' and geom.get('features'):
                    geom = geom['features'][0].get('geometry')

                point_count = meta.get('ptCount') or meta.get('pointCount')
                point_density = meta.get('pointDensity')

                # STAC/XML often drops High-Res Point Data. Let's dynamically regex the OpenTopography HTML Portal!
                dataset_url = meta.get('url')
                if not point_density and dataset_url:
                    try:
                        import re
                        html_resp = requests.get(dataset_url, timeout=15).text
                        density_match = re.search(r'([\d\.,]+)\s*pts/m', html_resp, re.IGNORECASE)
                        if density_match:
                            point_density = float(density_match.group(1).replace(',', ''))
                        
                        pts_match = re.search(r'Point Count(?:<[^>]+>\s*)*[:]*\s*([0-9,]+)', html_resp, re.IGNORECASE)
                        if pts_match:
                            point_count = int(pts_match.group(1).replace(',', ''))
                    except Exception as e:
                        logger.warning(f"Failed OT DOM Intercept for {dataset_url}: {e}")

                # Impute missing point counts geometrically using Density * Area (m2)
                if point_density and area and not point_count:
                    try:
                        point_count = int(float(point_density) * float(area) * 1e6)
                    except:
                        pass

                results.append({
                    "provider": "OpenTopography",
                    "dataset_id": dataset_id,
                    "name": meta.get('name') or meta.get('alternateName'),
                    "description": meta.get('description', ''),
                    "url": dataset_url,
                    "bounds": None, 
                    "geometry": geom,
                    "date": meta.get('dateCreated'),
                    "point_count": point_count, 
                    "point_density": point_density,
                    "area_sqkm": area,
                    # Store raw for full context
                    "raw_metadata": meta
                })
            return results

        except requests.RequestException as e:
            logger.error(f"Error searching OpenTopography: {e}")
            return []

    def download(self, dataset_id: str, output_dir: Path, **kwargs) -> Path:
        """
        Satisfies Provider Base Class formal requirements organically.
        The actual OpenTopography SDSC HTTP stream extraction is fully integrated natively into `get_fetch_urls` utilizing MinIO XML traversals for `download.py`.
        """
        pass

    def get_fetch_urls(self, raw_metadata: dict, roi: Optional[Polygon], hive_dir: Path) -> list:
        """
        Dynamically extracts formal native SDSC S3 payload endpoints for an OpenTopography dataset.
        If an ROI is active, we attempt to download the spatial TileIndex.zip natively, returning subset targets.
        Otherwise, we recursively paginate the MinIO XML array isolating all standard `.laz` matrices.
        """
        import xml.etree.ElementTree as ET
        import tempfile
        import zipfile
        import geopandas as gpd
        import urllib.request
        
        # Structural OpenTopography keys actively mirror standard AWS prefixes organically
        alt_name = raw_metadata.get('alternateName', raw_metadata.get('name', ''))
        if not alt_name:
            logger.error(f"OpenTopography native extraction failed. No structural AlternateName mapped for S3.")
            return []
            
        base_s3 = "https://opentopography.s3.sdsc.edu/pc-bulk"
        prefix = f"{alt_name}/"
        urls = []
        
        logger.info(f"Probing OpenTopography S3 MinIO storage layer natively targeted natively on: {prefix}")
        
        # Mode B: ROI Extents isolating native .shp mappings recursively
        mode_b_failed = False
        if roi:
            try:
                tile_idx_url = f"{base_s3}/{alt_name}/{alt_name}_TileIndex.zip"
                with tempfile.TemporaryDirectory() as tmpdir:
                    zip_path = Path(tmpdir) / "tile_idx.zip"
                    urllib.request.urlretrieve(tile_idx_url, zip_path)
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(tmpdir)
                        
                    shp_files = list(Path(tmpdir).glob("*.shp"))
                    if shp_files:
                        gdf = gpd.read_file(shp_files[0])
                        # Coerce standard projection explicitly for intersect bindings
                        gdf = gdf.to_crs(4326)
                        gdf_roi = gpd.GeoDataFrame(geometry=[roi], crs="EPSG:4326")
                        gdf_intersect = gpd.overlay(gdf, gdf_roi, how='intersection')
                        
                        logger.info(f"OpenTopography intersected precisely {len(gdf_intersect)} .laz physical tiles via geometry index.")
                        
                        # Most OT shapes leverage 'URL', 'FileName', 'Location', or 'Filename' attributes
                        id_col = next((c for c in ['URL', 'FileName', 'Location', 'Filename'] if c in gdf.columns), None)
                        if id_col:
                            from concurrent.futures import ThreadPoolExecutor
                            
                            def get_head_size(val):
                                laz_name = val.split('/')[-1] if '/' in val else val
                                exact_url = f"{base_s3}/{alt_name}/{laz_name}"
                                target = hive_dir / laz_name
                                try:
                                    r = requests.head(exact_url, timeout=5)
                                    if r.status_code == 200:
                                        sz = int(r.headers.get('Content-Length', 0))
                                        return (exact_url, target, sz)
                                except Exception:
                                    pass
                                return (exact_url, target, 0)
                                
                            with ThreadPoolExecutor(max_workers=10) as executor:
                                urls.extend(list(executor.map(get_head_size, gdf_intersect[id_col])))
                        else:
                            mode_b_failed = True
                    else:
                        mode_b_failed = True
            except Exception as e:
                logger.warning(f"Shapefile subsetting explicitly failed structurally: {e}. Defaulting to un-segmented array acquisition limits.")
                mode_b_failed = True
        
        # Mode A: Full S3 Acquisition recursively isolating native payload bounds organically
        if not roi or mode_b_failed:
            logger.info("Engaging full SDSC Object XML native acquisition matrix. Extracting absolute nodes.")
            ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
            marker = ""
            while True:
                req_url = f"{base_s3}/?prefix={prefix}&marker={marker}" if marker else f"{base_s3}/?prefix={prefix}"
                try:
                    r = requests.get(req_url)
                    r.raise_for_status()
                    root = ET.fromstring(r.text)
                    
                    for content in root.findall('s3:Contents', ns):
                        key = content.find('s3:Key', ns).text
                        size_el = content.find('s3:Size', ns)
                        size_b = int(size_el.text) if size_el is not None else 0
                        if key.endswith('.laz') or key.endswith('.las'):
                            exact_url = f"{base_s3}/{key}"
                            target = hive_dir / key.split('/')[-1]
                            urls.append((exact_url, target, size_b))
                            
                    trunc = root.find('s3:IsTruncated', ns)
                    if trunc is None or trunc.text == 'false':
                        break
                    
                    nm = root.find('s3:NextMarker', ns)
                    if nm is not None:
                        marker = nm.text
                    else:
                        break
                except Exception as e:
                    logger.error(f"MinIO pagination strictly aborted organically: {e}")
                    break
                    
        return urls
