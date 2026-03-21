import sys
import json
import csv
import logging
import shutil
import urllib.request
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from shapely.geometry import box

from als_finder.core.input_manager import load_roi
from als_finder.core.ept_parser import EPTParser

logger = logging.getLogger(__name__)

def generate_fetch_array(workspace_path: Path, roi_path: Optional[str], full_acquisition: bool) -> Path:
    """
    Parses manifest.json natively and calculates the explicit physical intersection matrix 
    for all target binaries, returning the generated CSV path.
    """
    manifest_path = workspace_path / 'catalog' / 'manifest.json'
    fetch_csv_path = workspace_path / 'catalog' / 'fetch_array.csv'
    
    if not manifest_path.exists():
        logger.error(f"Critical Error: No manifest.json found at {manifest_path}")
        sys.exit(1)
        
    logger.info(f"Mapped active manifest: {manifest_path}")
    
    with open(manifest_path, 'r') as f:
        try:
            manifest_data = json.load(f)
        except json.JSONDecodeError:
            logger.error("Failed to parse manifest.json JSON array.")
            sys.exit(1)
            
    datasets = manifest_data.get('datasets', [])
    if not datasets:
        logger.warning(f"Manifest structurally contains 0 datasets. Terminating gracefully.")
        sys.exit(0)
        
    # Isolate ROI Fallback mechanisms natively
    target_roi_path = roi_path or manifest_data.get('search_parameters', {}).get('roi')
    if not target_roi_path and not full_acquisition:
        logger.error("No ROI provided structurally. Use --roi or globally bypass via --full.")
        sys.exit(1)
        
    roi_poly = None
    if not full_acquisition:
        roi_poly = load_roi(target_roi_path)
        logger.info(f"Isolating geographical intersections mathematically across: {roi_poly.bounds}")
        
    logger.info(f"Parsed {len(datasets)} dataset(s). Commencing tile intersection protocols...")
    
    # Write the target extraction arrays mathematically
    with open(fetch_csv_path, 'w') as f:
        f.write("provider,dataset_id,source_url,target_path\n")
        
        for item in datasets:
            p_name = item.get('provider', 'UNKNOWN')
            d_name = item.get('dataset_id') or item.get('name', 'UNKNOWN')
            url = item.get('url') or item.get('ept_url') or ""
            
            hive_dir = workspace_path / 'data' / 'raw' / f"provider={p_name}" / f"dataset={d_name}"
            
            # EPT Subsetting physically isolates Octree bounds statically
            if "ept.json" in url and roi_poly is not None:
                parser = EPTParser(url)
                tiles = parser.find_intersecting_laz(roi_poly)
                logger.info(f"Intercepted {len(tiles)} intersecting tiles for {d_name}.")
                for (laz_url, count) in tiles:
                    node_id = laz_url.split('/')[-1]
                    hive_target = hive_dir / node_id
                    f.write(f"{p_name},{d_name},{laz_url},{hive_target.absolute()}\n")
            else:
                # Target the total comprehensive node root
                hive_target = hive_dir / f"{d_name}_subset.laz"
                f.write(f"{p_name},{d_name},{url},{hive_target.absolute()}\n")
        
    logger.info("================================================================================")
    logger.info(f"[SUCCESS] Generated target URI list: {fetch_csv_path}")
    logger.info("[WARNING] Dry-run generated. No physical binaries were formally downloaded.")
    logger.info("[WARNING] To automatically pull this payload, re-run exactly with: --execute")
    logger.info("================================================================================")
    
    return fetch_csv_path

def execute_fetch_array(workspace_path: Path) -> None:
    """
    Reads the statically generated fetch_array.csv and actively downloads 
    the targeted `.laz` URIs directly to the modeled local Hive layout.
    """
    fetch_csv_path = workspace_path / 'catalog' / 'fetch_array.csv'
    
    if not fetch_csv_path.exists():
        logger.error(f"Critical Error: No fetch_array.csv found. Formally generate the dry-run matrix first.")
        sys.exit(1)
        
    logger.info(f"Targeting fetch array: {fetch_csv_path}")
    total_bytes, used_bytes, free_bytes = shutil.disk_usage(workspace_path)
    logger.info(f"Verified local workspace capacity: {free_bytes / (1024**3):.2f} GB available.")
    
    with open(fetch_csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    if not rows:
        logger.info("Fetch array structurally empty. Nothing to download.")
        return
        
    def fetch_worker(row):
        source = row['source_url']
        target = Path(row['target_path'])
        
        if target.exists():
            return "SKIPPED"
            
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(source, target)
            return "SUCCESS"
        except Exception as e:
            logger.error(f"Failed to fetch {source}: {e}")
            return "FAILED"
            
    logger.info(f"Physically orchestrating multi-threaded download sequence for {len(rows)} nodes...")
    
    success_ct = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(fetch_worker, rows):
            if result in ["SUCCESS", "SKIPPED"]:
                success_ct += 1
                
    logger.info(f"[SUCCESS] Total Data Block Acquisition completed: {success_ct}/{len(rows)} matrices mapped.")
