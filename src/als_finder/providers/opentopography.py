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
    CACHE_DIR = Path.home() / ".cache" / "als_finder"
    CATALOG_CACHE_FILE = CACHE_DIR / "opentopography_catalog.json"
    DENSITY_CACHE_FILE = CACHE_DIR / "ot_density_cache.json"

    def __init__(self, ot_key: Optional[str] = None):
        """Initializes the OpenTopography abstraction using unified credential resolver."""
        from als_finder.core.auth_manager import resolve_credential
        self.api_key = resolve_credential(
            env_var_name="OPENTOPOGRAPHY_API_KEY",
            cli_value=ot_key,
            provider_name="OpenTopography",
            signup_url="https://portal.opentopography.org/myopentopo",
            instructions=[
                "Create a free account at: https://portal.opentopography.org/myopentopo",
                "Navigate to 'My Account' -> 'OpenTopography API Key'.",
                "Click 'Request an API Key' and copy the alphanumeric key string.",
                "Pass it once via CLI to auto-cache in your workspace: als-finder search --roi <file> --ot-key <YOUR_KEY>"
            ],
            auto_save_workspace_env=True
        )

    def check_access(self) -> bool:
        """Check if OpenTopography catalog cache or public otCatalog endpoint is reachable."""
        if self.CATALOG_CACHE_FILE.exists() and self.CATALOG_CACHE_FILE.stat().st_size > 1000:
            return True
        try:
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

            import json
            import re
            from concurrent.futures import ThreadPoolExecutor

            density_cache: Dict[str, Dict[str, Any]] = {}
            if self.DENSITY_CACHE_FILE.exists():
                try:
                    with open(self.DENSITY_CACHE_FILE, "r", encoding="utf-8") as cf:
                        density_cache = json.load(cf)
                except Exception:
                    density_cache = {}

            results = []
            urls_to_scrape: List[str] = []

            for ds in datasets:
                # OpenTopography wraps the actual metadata in a 'Dataset' key using JSON-LD
                meta = ds.get('Dataset', ds)
                
                # Extract IDs natively from the JSON-LD format (preferring S3 prefix alternateName like CA18_Thompson)
                ident = meta.get('identifier', {})
                if isinstance(ident, dict):
                    raw_ident = str(ident.get('value', 'Unknown'))
                else:
                    raw_ident = str(ident)
                alt_name_val = str(meta.get('alternateName') or '').strip()
                dataset_id = alt_name_val if alt_name_val else raw_ident
                    
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
                    
                # Precision filter: ensure the exact flight polygon intersects the ROI
                if geom and roi:
                    from shapely.geometry import shape
                    try:
                        ot_poly = shape(geom)
                        if not ot_poly.intersects(roi):
                            logger.debug(f"OpenTopography dataset {dataset_id} intersects API bbox but precise geometry avoids ROI. Dropping.")
                            continue
                    except Exception as e:
                        logger.warning(f"Failed to parse OT precise geometry for {dataset_id}: {e}")

                point_count = meta.get('ptCount') or meta.get('pointCount')
                point_density = meta.get('pointDensity')
                dataset_url = meta.get('url')

                if not point_density and dataset_url:
                    if dataset_url in density_cache:
                        point_density = density_cache[dataset_url].get("point_density")
                        if not point_count:
                            point_count = density_cache[dataset_url].get("point_count")
                    else:
                        urls_to_scrape.append(dataset_url)

                # Extract flight date from temporalCoverage when available (more accurate than portal dateCreated)
                temp_cov = str(meta.get('temporalCoverage') or '').strip()
                acq_date = meta.get('dateCreated')
                if temp_cov:
                    date_matches = re.findall(r'\d{4}-\d{2}-\d{2}', temp_cov)
                    if date_matches:
                        acq_date = date_matches[-1]

                clean_meta = self.sanitize_metadata(meta)
                clean_meta["ot_id"] = raw_ident
                clean_meta["alternateName"] = dataset_id
                if temp_cov:
                    clean_meta["temporalCoverage"] = temp_cov

                results.append({
                    "provider": "OpenTopography",
                    "dataset_id": dataset_id,
                    "name": meta.get('name') or meta.get('alternateName') or dataset_id,
                    "description": meta.get('description', ''),
                    "url": dataset_url,
                    "bounds": None, 
                    "geometry": geom,
                    "date": acq_date,
                    "point_count": point_count, 
                    "point_density": point_density,
                    "area_sqkm": area,
                    "raw_metadata": clean_meta,
                    "additional_metadata": clean_meta
                })

            if urls_to_scrape:
                def _scrape_one(u: str):
                    p_dens, p_cnt = None, None
                    try:
                        html_resp = requests.get(u, timeout=8).text
                        density_match = re.search(r'([\d\.,]+)\s*pts/m', html_resp, re.IGNORECASE)
                        if density_match:
                            p_dens = float(density_match.group(1).replace(',', ''))
                        pts_match = re.search(r'Point Count(?:<[^>]+>\s*)*[:]*\s*([0-9,]+)', html_resp, re.IGNORECASE)
                        if pts_match:
                            p_cnt = int(pts_match.group(1).replace(',', ''))
                    except Exception as e:
                        logger.debug(f"Failed OT DOM Intercept for {u}: {e}")
                    return u, {"point_density": p_dens, "point_count": p_cnt}

                with ThreadPoolExecutor(max_workers=8) as pool:
                    for u, scraped in pool.map(_scrape_one, urls_to_scrape):
                        density_cache[u] = scraped

                try:
                    self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    with open(self.DENSITY_CACHE_FILE, "w", encoding="utf-8") as cf:
                        json.dump(density_cache, cf)
                except Exception:
                    pass

            for item in results:
                u = item.get("url")
                if not item.get("point_density") and u and u in density_cache:
                    item["point_density"] = density_cache[u].get("point_density")
                    if not item.get("point_count"):
                        item["point_count"] = density_cache[u].get("point_count")
                if not item.get("point_density"):
                    dt_str = str(item.get("date") or "")
                    yr_match = re.search(r'(20\d{2}|199\d)', dt_str or str(item.get("dataset_id") or ""))
                    if yr_match and int(yr_match.group(1)) >= 2012:
                        item["point_density"] = 8.5
                if item.get("point_density") and item.get("area_sqkm") and not item.get("point_count"):
                    try:
                        item["point_count"] = int(float(item["point_density"]) * float(item["area_sqkm"]) * 1e6)
                    except Exception:
                        pass

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

    def get_pdal_reader(
        self,
        urls: List[str],
        buffered_poly: Polygon,
        poly_crs: Optional[str] = None,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        import geopandas as gpd
        pipeline = []
        inputs = []
        if poly_crs and poly_crs.upper() != "EPSG:3857":
            ept_poly = gpd.GeoDataFrame(geometry=[buffered_poly], crs=poly_crs).to_crs("EPSG:3857").geometry.iloc[0]
        else:
            ept_poly = buffered_poly
        eb_minx, eb_miny, eb_maxx, eb_maxy = ept_poly.bounds
        ept_bounds_str = f"([{eb_minx}, {eb_maxx}], [{eb_miny}, {eb_maxy}])"

        resolved_urls: List[str] = []
        ds_id_hint = kwargs.get("dataset_id")
        for u in urls:
            u_low = str(u).lower()
            if u_low.endswith("ept.json") or u_low.endswith(".laz") or u_low.endswith(".las"):
                resolved_urls.append(str(u))
            else:
                if ds_id_hint:
                    alt_name = str(ds_id_hint)
                elif "dsid=" in str(u):
                    alt_name = str(u).split("dsid=")[-1].split("&")[0].strip("/")
                else:
                    alt_name = str(u).rstrip("/").split("/")[-1]
                roi_wgs = (
                    gpd.GeoDataFrame(geometry=[buffered_poly], crs=poly_crs).to_crs("EPSG:4326").geometry.iloc[0]
                    if poly_crs else buffered_poly
                )
                fetched = self.get_fetch_urls({"alternateName": alt_name}, roi_wgs, Path("/tmp"))
                if fetched:
                    resolved_urls.extend([item[0] for item in fetched])
                else:
                    resolved_urls.append(str(u))

        for i, url in enumerate(resolved_urls):
            tag = f"reader_{i}"
            u_low = url.lower()
            if u_low.endswith("ept.json"):
                pipeline.append({
                    "type": "readers.ept",
                    "filename": url,
                    "bounds": ept_bounds_str,
                    "tag": tag
                })
            elif poly_crs is not None and not u_low.endswith(".copc.laz") and (u_low.endswith(".laz") or u_low.endswith(".las")):
                pipeline.append({
                    "type": "readers.las",
                    "filename": url,
                    "tag": tag
                })
            else:
                pipeline.append({
                    "type": "readers.copc",
                    "filename": url,
                    "polygon": buffered_poly.wkt,
                    "tag": tag
                })
            inputs.append(tag)
            
        if len(resolved_urls) > 1:
            pipeline.append({
                "type": "filters.merge",
                "inputs": inputs
            })
        return pipeline

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
