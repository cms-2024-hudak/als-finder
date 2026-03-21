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
    fetch_matrix_manifest = {}
    total_estimated_bytes = 0
    total_tiles = 0
    
    with open(fetch_csv_path, 'w') as f:
        f.write("provider,dataset_id,source_url,target_path\n")
        
        for item in datasets:
            p_name = item.get('provider', 'UNKNOWN')
            d_name = item.get('dataset_id') or item.get('name', 'UNKNOWN')
            url = item.get('url') or item.get('ept_url') or ""
            
            if d_name not in fetch_matrix_manifest:
                fetch_matrix_manifest[d_name] = {
                    "Provider": p_name,
                    "Name": d_name,
                    "Tiles": 0,
                    "Bytes": 0,
                    "Format": ".laz"
                }
                
            hive_dir = workspace_path / 'data' / 'raw' / f"provider={p_name}" / f"dataset={d_name}"
            
            if p_name.lower() == "opentopography":
                from als_finder.providers.opentopography import OpenTopographyProvider
                provider = OpenTopographyProvider()
                ot_urls = provider.get_fetch_urls(item.get('raw_metadata', {}), roi_poly, hive_dir)
                for source_url, target_path, byte_sz in ot_urls:
                    f.write(f"{p_name},{d_name},{source_url},{target_path.absolute()}\n")
                    fetch_matrix_manifest[d_name]["Bytes"] += byte_sz
                    fetch_matrix_manifest[d_name]["Tiles"] += 1
                    fetch_matrix_manifest[d_name]["Format"] = Path(target_path).suffix
                    total_estimated_bytes += byte_sz
                    total_tiles += 1
            # EPT Subsetting physically isolates Octree bounds statically
            elif "ept.json" in url and roi_poly is not None:
                parser = EPTParser(url)
                tiles = parser.find_intersecting_laz(roi_poly)
                logger.info(f"Intercepted {len(tiles)} intersecting tiles for {d_name}.")
                for (laz_url, count) in tiles:
                    node_id = laz_url.split('/')[-1]
                    hive_target = hive_dir / node_id
                    f.write(f"{p_name},{d_name},{laz_url},{hive_target.absolute()}\n")
                    est_sz = (int(count) * 8) if count else 0
                    fetch_matrix_manifest[d_name]["Bytes"] += est_sz
                    fetch_matrix_manifest[d_name]["Tiles"] += 1
                    total_estimated_bytes += est_sz
                    total_tiles += 1
            else:
                # Target the total comprehensive node root
                hive_target = hive_dir / f"{d_name}_subset.laz"
                f.write(f"{p_name},{d_name},{url},{hive_target.absolute()}\n")
                
                est_sz = int(item.get('size', 0))
                fetch_matrix_manifest[d_name]["Bytes"] += est_sz
                fetch_matrix_manifest[d_name]["Tiles"] += 1
                total_estimated_bytes += est_sz
                total_tiles += 1
        
    def format_sz(b):
        gb = b / (1024**3)
        if gb >= 1.0: return f"{gb:.2f} GB"
        return f"{b / (1024**2):.2f} MB"
        
    col_widths = {"Provider": 15, "Name": 38, "Tiles": 8, "True Size": 12, "Format": 8}
    header = f" | {'Provider':<{col_widths['Provider']}} | {'Name':<{col_widths['Name']}} | {'Tiles':>{col_widths['Tiles']}} | {'True Size':>{col_widths['True Size']}} | {'Format':>{col_widths['Format']}} |"
    
    print("\n" + "=" * len(header))
    print(" LiDAR Fetch Array Matrix ")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    
    for k, v in fetch_matrix_manifest.items():
        prov = v["Provider"][:col_widths["Provider"]]
        name = v["Name"][:col_widths["Name"]]
        tiles = str(v["Tiles"])
        sz_str = format_sz(v["Bytes"])
        fmt = v["Format"]
        print(f" | {prov:<{col_widths['Provider']}} | {name:<{col_widths['Name']}} | {tiles:>{col_widths['Tiles']}} | {sz_str:>{col_widths['True Size']}} | {fmt:>{col_widths['Format']}} |")
        
    print("=" * len(header))
    print(f" TOTAL ACQUISITIONS: {len(fetch_matrix_manifest)} | PHYSICAL TILES: {total_tiles} | EXPECTED PAYLOAD: {format_sz(total_estimated_bytes)}")
    print("-" * len(header))
    print(f" FETCH TARGET URI: {fetch_csv_path}")
    print("================================================================================\n")
    
    logger.info(f"[SUCCESS] Array Generation Protocol Complete.")
    logger.info("[WARNING] Dry-run natively executed. No physical binaries were formally downloaded to your hard drive.")
    logger.info("[WARNING] To gracefully pull these payloads natively, execute exactly with: --execute")
    
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
