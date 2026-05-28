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

logger = logging.getLogger(__name__)

def generate_fetch_array(workspace_path: Path, roi_path: str = None, full_acquisition: bool = False, execute: bool = False) -> Path:
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
        
        import pyproj
        from shapely.ops import transform
        # Buffer 50m to mitigate downstream edge artifacts (Issue #9)
        project_to_metric = pyproj.Transformer.from_crs(pyproj.CRS('EPSG:4326'), pyproj.CRS('EPSG:3857'), always_xy=True).transform
        project_to_wgs84 = pyproj.Transformer.from_crs(pyproj.CRS('EPSG:3857'), pyproj.CRS('EPSG:4326'), always_xy=True).transform
        
        roi_metric = transform(project_to_metric, roi_poly)
        roi_metric_buffered = roi_metric.buffer(50.0)
        roi_poly = transform(project_to_wgs84, roi_metric_buffered)
        
        logger.info(f"Isolating geographical intersections mathematically across 50m buffered bounds: {roi_poly.bounds}")
        
    logger.info(f"Parsed {len(datasets)} dataset(s). Commencing tile intersection protocols...")
    
    # Write the target extraction arrays mathematically
    fetch_matrix_manifest = {}
    total_estimated_bytes = 0
    total_tiles = 0
    
    with open(fetch_csv_path, 'w') as f:
        f.write("provider,dataset_id,source_url,target_path,est_size\n")
        
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
                    f.write(f"{p_name},{d_name},{source_url},{target_path.absolute()},{byte_sz}\n")
                    fetch_matrix_manifest[d_name]["Bytes"] += byte_sz
                    fetch_matrix_manifest[d_name]["Tiles"] += 1
                    fetch_matrix_manifest[d_name]["Format"] = Path(target_path).suffix
                    total_estimated_bytes += byte_sz
                    total_tiles += 1
            # EPT Subsetting dynamically integrates with PDAL readers.ept natively
            elif "ept.json" in url and roi_poly is not None:
                import pyproj
                import requests
                from shapely.ops import transform
                
                # Dynamically determine the native CRS of the EPT dataset to prevent 0-point downloads
                native_crs = "EPSG:3857" # Default fallback (Common for USGS)
                try:
                    ept_resp = requests.get(url, timeout=5)
                    if ept_resp.status_code == 200:
                        srs_info = ept_resp.json().get('srs', {})
                        if 'authority' in srs_info and 'horizontal' in srs_info:
                            native_crs = f"{srs_info['authority']}:{srs_info['horizontal']}"
                        elif 'wkt' in srs_info:
                            native_crs = srs_info['wkt']
                except Exception as e:
                    logger.warning(f"Failed to fetch native EPT CRS for {d_name}. Falling back to EPSG:3857: {e}")
                
                project = pyproj.Transformer.from_crs(pyproj.CRS('EPSG:4326'), pyproj.CRS(native_crs), always_xy=True).transform
                roi_native = transform(project, roi_poly)
                
                # Target the total comprehensive node root mathematically via native pipeline extraction
                hive_target = hive_dir / f"{d_name}_subset.laz"
                minx, miny, maxx, maxy = roi_native.bounds
                bounds_str = f"([{minx:.4f}, {maxx:.4f}], [{miny:.4f}, {maxy:.4f}])"
                
                # For EPT Subsets, the physical download size is unknown until the stream finishes.
                # Do NOT use the massive STAC size attribute, otherwise the progress bar will expect terabytes.
                est_sz = 0
                
                # Encode bounds safely into target_path placeholder natively
                f.write(f"{p_name},{d_name},{url},\"{hive_target.absolute()}|{bounds_str}\",{est_sz}\n")
                
                fetch_matrix_manifest[d_name]["Bytes"] += est_sz
                fetch_matrix_manifest[d_name]["Tiles"] += 1
                total_estimated_bytes += est_sz
                total_tiles += 1
            else:
                # Target the total comprehensive node root
                hive_target = hive_dir / f"{d_name}_subset.laz"
                est_sz = int(item.get('size', 0))
                f.write(f"{p_name},{d_name},{url},{hive_target.absolute()},{est_sz}\n")
                
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
    
    if not execute:
        import click
        click.secho("[NOTICE] Dry-run only. Review the table above, refine your search if necessary, or run the exact same command with the --execute flag to begin physical download.", fg="yellow", bold=True)
    
    return fetch_csv_path

def execute_fetch_array(workspace_path: Path, workers: int = None, overwrite: bool = False):
    """
    Physically execute the fetch array natively, pulling LiDAR binaries directly to local disk.
    """
    fetch_csv_path = workspace_path / 'catalog' / 'fetch_array.csv'
    
    if not fetch_csv_path.exists():
        logger.error(f"Missing fetch array in {workspace_path}. Run fetch generation first.")
        return
        
    import csv
    import requests
    import shutil
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    import os
    
    logger.info(f"Targeting fetch array: {fetch_csv_path}")
    total_bytes, used_bytes, free_bytes = shutil.disk_usage(workspace_path)
    logger.info(f"Verified local workspace capacity: {free_bytes / (1024**3):.2f} GB available.")
    
    with open(fetch_csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    if not rows:
        logger.info("Fetch array structurally empty. Nothing to download.")
        return
        
    total_est_bytes = 0
    for r in rows:
        try:
            total_est_bytes += int(r.get('est_size', 0))
        except ValueError:
            pass

    import click
    from tqdm import tqdm
    ctx = click.get_current_context(silent=True)
    disable_tqdm = ctx.params.get('quiet', False) if ctx and hasattr(ctx, 'params') else False

    pbar = tqdm(total=total_est_bytes, unit='iB', unit_scale=True, desc="Downloading payloads", disable=disable_tqdm)
    lock = threading.Lock()

    def fetch_worker(row):
        source = row['source_url']
        target_raw = row['target_path']
        
        try:
            est_size = int(row.get('est_size', 0))
        except ValueError:
            est_size = 0
            
        # Unpack embedded bounds for EPT natively
        bounds_str = None
        if '|' in target_raw:
            target_str, bounds_str = target_raw.split('|')
            target = Path(target_str)
        else:
            target = Path(target_raw)
            
        if target.exists() and not overwrite:
            if est_size > 0:
                with lock:
                    pbar.update(est_size)
            return "SKIPPED"
            
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if "ept.json" in source:
                import subprocess
                # Using resolution=0 enforces max LOD directly from the cloud natively
                pdal_cmd = [
                    'pdal', 'translate',
                    source,
                    str(target),
                    '--stream'
                ]
                if bounds_str:
                    pdal_cmd.extend(['--readers.ept.bounds=' + bounds_str])
                pdal_cmd.extend(['--readers.ept.resolution=0'])
                pdal_cmd.extend(['--readers.ept.threads=2'])
                # We do NOT use COPC writers during download to save massive memory overhead.
                # COPC formatting will be handled entirely during the Standardization phase.
                
                logger.info(f"Dynamically streaming EPT natively: {' '.join(pdal_cmd)}")
                
                # Option B: Write stderr to a temporary log file to prevent pipe deadlocks
                log_file_path = target.with_suffix('.log')
                with open(log_file_path, 'w') as log_file:
                    proc = subprocess.Popen(pdal_cmd, stdout=subprocess.DEVNULL, stderr=log_file)
                    
                    # File polling thread for pdal translate to dynamically update byte-progress
                    last_size = 0
                    while proc.poll() is None:
                        time.sleep(1)
                        if target.exists():
                            cur_size = os.path.getsize(target)
                            diff = cur_size - last_size
                            if diff > 0:
                                with lock:
                                    pbar.update(diff)
                            last_size = cur_size
                            
                # Wait cleanly to reap the process
                proc.wait()
                
                if proc.returncode != 0:
                    err = ""
                    if log_file_path.exists():
                        with open(log_file_path, 'r') as log_file:
                            err = log_file.read()
                    logger.error(f"PDAL extraction failed natively for {source}: {err}")
                    if log_file_path.exists():
                        log_file_path.unlink()
                    return "FAILED"
                    
                if log_file_path.exists():
                    log_file_path.unlink()
                    
                # Post-download safeguard: automatically purge 0-point ghost extractions
                if target.exists() and os.path.getsize(target) < 2048:
                    logger.warning(f"0 points found in geometric subset for {source}. Purging 1kb ghost artifact.")
                    target.unlink()
                    return "EMPTY"
                    
                # Flush remaining bytes
                if target.exists():
                    cur_size = os.path.getsize(target)
                    diff = cur_size - last_size
                    if diff > 0:
                        with lock:
                            pbar.update(diff)
                return "SUCCESS"
            else:
                # Direct HTTP Chunking
                with requests.get(source, stream=True) as r:
                    r.raise_for_status()
                    with target.open('ab') as file:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk:
                                file.write(chunk)
                                with lock:
                                    pbar.update(len(chunk))
                return "SUCCESS"
        except Exception as e:
            logger.error(f"Failed to fetch {source}: {e}")
            return "FAILED"
            
    # Dynamically calculate Safe Network Workers
    if workers is None:
        # For maximum safety and performance, we default to 1 python worker globally.
        # This serializes the python loops but allows highly-parallel tools like PDAL
        # to freely use all 16+ native CPU cores internally without risking OOM crashes.
        workers = 1
            
    logger.info(f"Physically orchestrating multi-threaded download sequence for {len(rows)} nodes using {workers} concurrent workers...")
    
    success_ct = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = executor.map(fetch_worker, rows)
        for result in results:
            if result in ["SUCCESS", "SKIPPED"]:
                success_ct += 1
                
    pbar.close()
    logger.info(f"[SUCCESS] Total Data Block Acquisition completed: {success_ct}/{len(rows)} matrices mapped.")
