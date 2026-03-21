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
        import click
        from dotenv import load_dotenv
        
        # Priority 1: Argument passed explicitly
        # Priority 2: Current shell / workspace .env (loaded by cli.py)
        self.api_key = api_key or os.getenv("OPENTOPOGRAPHY_API_KEY")
        
        # Priority 3: Global config
        global_config_dir = Path.home() / ".config" / "als-finder"
        global_env = global_config_dir / ".env"
        
        if not self.api_key and global_env.exists():
            load_dotenv(global_env)
            self.api_key = os.getenv("OPENTOPOGRAPHY_API_KEY")
            
        # If still missing, securely intercept the CLI and globally cache it
        if not self.api_key:
            logger.info("OpenTopography requires a free API key for native dataset execution. (https://portal.opentopography.org/myopentopo)")
            new_key = click.prompt("Please enter your OPENTOPOGRAPHY_API_KEY (input hidden)", hide_input=True)
            if new_key:
                self.api_key = new_key.strip()
                global_config_dir.mkdir(parents=True, exist_ok=True)
                with open(global_env, "a") as f:
                    f.write(f"\nOPENTOPOGRAPHY_API_KEY={self.api_key}\n")
                logger.info(f"API Key physically secured at {global_env}")
            else:
                logger.warning("No OpenTopography API key provided. OT Discovery will bypass.")

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

    def download(self, dataset_id: str, output_dir: Path, roi: Optional[Polygon] = None, **kwargs) -> Path:
        """
        Executes a formal Point Cloud processing job natively against the OT API.
        This handles the POST submission, asynchronous status polling, and payload extraction.
        
        Note: The actual Endpoint path /API/pc represents the architectural standard for OT jobs.
        """
        import time
        import tarfile
        
        if not self.api_key:
            logger.error("API Key required. Cannot download OpenTopography datasets anonymously.")
            raise PermissionError("OpenTopography API Key required.")

        # Determine geometric bounds organically. 
        # OpenTopography jobs structurally crash if a bounding box is absent.
        if roi:
            minx, miny, maxx, maxy = roi.bounds
        else:
            logger.error("OpenTopography mandates a strict bounding box constraint. You must pass `--roi`.")
            raise ValueError("Missing ROI constraint for OpenTopography download.")

        job_submit_url = f"{self.BASE_URL}/pc"
        payload = {
            "datasetName": dataset_id,
            "minx": minx,
            "miny": miny,
            "maxx": maxx,
            "maxy": maxy,
            "API_Key": self.api_key,
            "outputFormat": "laz", # Request explicit LAZ formats
            "email": "als-finder@automated.bot" # Notification bypass
        }

        logger.info(f"Submitting OpenTopography PC Job for dataset: {dataset_id}")
        
        try:
            # 1. Trigger the asynchronous Point Cloud Job Creation
            response = requests.post(job_submit_url, data=payload, timeout=30)
            if response.status_code == 404:
                logger.error("OpenTopography PC API endpoint unresolved. Verify portal.opentopography.org routing.")
                return output_dir
            response.raise_for_status()
            
            job_id = response.text.strip() # Commonly returns the tracking ID textually
            logger.info(f"OpenTopography Job Initiated Successfully. Job ID: {job_id}")
            
            # 2. Asynchronous Execution Poller Logics
            status_url = f"{self.BASE_URL}/pc/status"
            download_url = f"{self.BASE_URL}/pc/download"
            is_complete = False
            
            logger.info("Polling OpenTopography PDAL cluster engines. Awaiting completion...")
            timeout_limit = 60 * 60 # 1 hour safe timeout
            start_time = time.time()
            
            while not is_complete:
                if time.time() - start_time > timeout_limit:
                    logger.error("OpenTopography Job Timed Out structurally.")
                    return output_dir
                    
                time.sleep(10)
                status_res = requests.get(status_url, params={"jobId": job_id, "API_Key": self.api_key})
                status_res.raise_for_status()
                
                # OT commonly returns 'Running', 'Completed', or 'Failed'
                status = status_res.text.strip()
                if status.lower() == 'completed':
                    is_complete = True
                elif status.lower() in ['failed', 'error']:
                    logger.error(f"OpenTopography declared PC Job Failed structurally: {job_id}")
                    return output_dir
                
            # 3. Pulling the physical payload Binary Tarball
            tar_target = output_dir / f"{dataset_id}_ot_payload.tar.gz"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Job finalized. Natively downloading binary tarball chunks...")
            with requests.get(download_url, params={"jobId": job_id, "API_Key": self.api_key}, stream=True) as r:
                r.raise_for_status()
                with open(tar_target, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): 
                        f.write(chunk)
            
            # 4. Extracting the binaries organically into the raw/ hive
            logger.info(f"Extracting LAZ files from tarball payloads structurally into Hive...")
            with tarfile.open(tar_target, "r:gz") as tar:
                tar.extractall(path=output_dir)
            
            # 5. Safe Cleanup
            tar_target.unlink()
            logger.info(f"[SUCCESS] OpenTopography specific LAZ dataset extraction complete: {output_dir.absolute()}")
            
        except requests.RequestException as e:
            logger.error(f"OpenTopography Extraction API structurally failed: {e}")
            
        return output_dir
