import logging
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional, List, Tuple
import geopandas as gpd
from shapely.geometry import Polygon, box

logger = logging.getLogger(__name__)

def execute_with_memory_limit(cmd: List[str], input_data: bytes, memory_limit_mb: int = 1536) -> Tuple[bool, str]:
    memory_limit_bytes = memory_limit_mb * 1024 * 1024
    
    # Prevent virtual memory explosion from thread allocation by restricting underlying C++ multi-threading.
    # PDAL pipeline instances are single-threaded workflows natively, but underlying libraries (OpenBLAS/GDAL) 
    # try to spawn 16+ threads, crashing the strict RLIMIT_AS constraint on stack allocation.
    pdal_env = os.environ.copy()
    pdal_env["OPENBLAS_NUM_THREADS"] = "1"
    pdal_env["OMP_NUM_THREADS"] = "1"
    pdal_env["GDAL_NUM_THREADS"] = "1"
    
    if sys.platform != 'win32':
        # We wrap the command in a tiny Python invocation that sets the memory limit natively,
        # then execvp() into the original command. This avoids using preexec_fn which forces
        # an unsafe fork() in multithreaded parent processes and can cause immediate OOMs.
        wrapper_cmd = [
            "python3", "-c",
            f"import sys, resource, os; resource.setrlimit(resource.RLIMIT_AS, ({memory_limit_bytes}, {memory_limit_bytes})); os.execvp(sys.argv[1], sys.argv[1:])"
        ] + cmd
        
        try:
            res = subprocess.run(wrapper_cmd, input=input_data, capture_output=True, env=pdal_env, check=True)
            return True, res.stderr.decode('utf-8')
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8')
            if e.returncode == -9 or e.returncode == -6 or "bad_alloc" in err_msg.lower() or "memory" in err_msg.lower():
                raise MemoryError(f"OS Memory Limit Exceeded ({memory_limit_mb}MB). Err: {err_msg}")
            return False, err_msg
    else:
        import psutil
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=pdal_env)
        
        oom_killed = {"killed": False}
        def monitor():
            try:
                p = psutil.Process(proc.pid)
                while proc.poll() is None:
                    try:
                        if p.memory_info().rss > memory_limit_bytes:
                            proc.kill()
                            oom_killed["killed"] = True
                            break
                    except psutil.NoSuchProcess:
                        break
                    time.sleep(0.5)
            except Exception:
                pass
                
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
        
        stdout, stderr = proc.communicate(input=input_data)
        
        if oom_killed["killed"]:
            raise MemoryError(f"Windows psutil Memory Limit Exceeded ({memory_limit_mb}MB)")
            
        if proc.returncode != 0:
            return False, stderr.decode('utf-8')
            
        return True, stderr.decode('utf-8')

def generate_grid(gdf: gpd.GeoDataFrame, tile_size: int = 512, buffer_size: int = 50) -> List[Tuple[Polygon, Polygon]]:
    """
    Generates a uniform vector grid over the total bounds of the provided GeoDataFrame.
    Assumes the GeoDataFrame is already in a metric CRS (e.g., EPSG:3857).
    Returns a list of tuples: (core_polygon, buffered_polygon).
    """
    minx, miny, maxx, maxy = gdf.total_bounds
    
    # Snap to nearest tile_size to create a uniform grid
    import math
    minx = math.floor(minx / tile_size) * tile_size
    miny = math.floor(miny / tile_size) * tile_size
    maxx = math.ceil(maxx / tile_size) * tile_size
    maxy = math.ceil(maxy / tile_size) * tile_size
    
    grid = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            core_poly = box(x, y, x + tile_size, y + tile_size)
            buffered_poly = box(x - buffer_size, y - buffer_size, x + tile_size + buffer_size, y + tile_size + buffer_size)
            grid.append((core_poly, buffered_poly))
            y += tile_size
        x += tile_size
        
    return grid

def run_pdal_standardization(
    raw_index_path: Path, 
    out_path: Path,
    crs: str, 
    core_poly: Polygon,
    buffered_poly: Polygon,
    provider: str = 'UNKNOWN',
    grid_crs: str = 'EPSG:3857',
    classifier: str = 'smrf',
    point_density: float = None
) -> bool:
    """
    Constructs and executes a PDAL pipeline to standardize a single tile from the tindex.
    Applies reprojection, ASPRS classification standardization, SMRF, HAG_NN, and crops to the core.
    """
    if out_path.exists():
        logger.info(f"Skipping {out_path.name} - already exists (Idempotency)")
        return True
        
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Bounding boxes for readers and crops
    b_minx, b_miny, b_maxx, b_maxy = buffered_poly.bounds
    c_minx, c_miny, c_maxx, c_maxy = core_poly.bounds
    
    buffered_bounds_str = f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])"
    core_bounds_str = f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])"
    
    # 1. Read the GeoPackage index to get remote URLs dynamically
    try:
        gdf = gpd.read_file(raw_index_path)
        # Intersect with buffered poly to find relevant files
        intersecting = gdf[gdf.intersects(buffered_poly)]
        if intersecting.empty:
            return True # Nothing to process for this tile
        urls = intersecting['location'].tolist()
    except Exception as e:
        logger.error(f"Failed to read index {raw_index_path}: {e}")
        return False

    process_pipeline = []
    
    # 2. Provider-specific Native Readers (or Local File Fallback)
    from als_finder.providers import get_provider
    try:
        # If the URL is a remote HTTP endpoint, delegate to the provider plugin
        if str(urls[0]).startswith("http"):
            provider_instance = get_provider(provider)
            reader_stages = provider_instance.get_pdal_reader(urls, buffered_poly)
            process_pipeline.extend(reader_stages)
        else:
            # It's a local downloaded file! Bypass the plugin and read natively.
            inputs = []
            for i, url in enumerate(urls):
                tag = f"reader_{i}"
                reader_type = "readers.copc" if str(url).lower().endswith(".copc.laz") else "readers.las"
                process_pipeline.append({
                    "type": reader_type,
                    "filename": url,
                    "tag": tag
                })
                inputs.append(tag)
                
            if len(urls) > 1:
                process_pipeline.append({
                    "type": "filters.merge",
                    "inputs": inputs
                })
    except Exception as e:
        logger.error(f"Failed to instantiate provider or build reader: {e}")
        return False
    
    # 3. Reprojection filter (from native CRS)
    if crs:
        target_crs = crs
        if crs.lower() == 'auto-utm':
            import math
            # Since core_poly is in EPSG:3857, we must reproject its centroid to 4326 to find UTM zone
            from pyproj import Transformer
            transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
            centroid = core_poly.centroid
            lon, lat = transformer.transform(centroid.x, centroid.y)
            zone = math.floor((lon + 180) / 6.0) + 1
            epsg = 32600 + zone if lat >= 0 else 32700 + zone
            target_crs = f"EPSG:{epsg}"
            
        process_pipeline.append({
            "type": "filters.reprojection",
            "out_srs": target_crs
        })
        
        # We also need to reproject our 3857 core bounds into the target CRS for the final crop!
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:3857", target_crs, always_xy=True)
        c_minx, c_miny = transformer.transform(c_minx, c_miny)
        c_maxx, c_maxy = transformer.transform(c_maxx, c_maxy)
        # Ensure min/max are correct after projection
        c_minx, c_maxx = min(c_minx, c_maxx), max(c_minx, c_maxx)
        c_miny, c_maxy = min(c_miny, c_maxy), max(c_miny, c_maxy)
        core_bounds_str = f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])"
        
    # 4. Density-Agnostic Noise Filtering
    process_pipeline.append({
        "type": "filters.expression",
        "expression": "Classification != 7 && Classification != 18 && ReturnNumber > 0 && NumberOfReturns > 0"
    })
    
    # 5. Statistical outlier filter
    process_pipeline.append({
        "type": "filters.outlier",
        "method": "statistical",
        "mean_k": 12,
        "multiplier": 3.0
    })
    
    # 6. Scientific Taxonomy Overwrite
    process_pipeline.append({
        "type": "filters.assign",
        "assignment": "Classification[:]=1"
    })
    # 7. Dynamic Ground Classification
    if classifier != 'none':
        # Dynamic density scaling
        if point_density is None or point_density >= 5.0:
            cell_size = 1.0
            threshold = 0.2
        elif point_density >= 1.0:
            cell_size = 2.0
            threshold = 0.4
        else:
            cell_size = 3.0
            threshold = 0.5
            
        if classifier == 'smrf':
            process_pipeline.append({
                "type": "filters.smrf",
                "cell": cell_size,
                "window": 18.0,
                "slope": 0.15,
                "threshold": threshold
            })
        elif classifier == 'csf':
            process_pipeline.append({
                "type": "filters.csf",
                "resolution": cell_size,
                "step": 0.5
            })
    
    # 8. Compute Height Above Ground (HAG)
    process_pipeline.append({
        "type": "filters.hag_nn"
    })
    
    # 9. Precision crop down to the core bounds (stripping the 50m buffer)
    process_pipeline.append({
        "type": "filters.crop",
        "bounds": core_bounds_str
    })
        
    # 10. Target Writer
    process_pipeline.append({
        "type": "writers.las",
        "filename": str(out_path.absolute()),
        "compression": "laszip",
        "a_srs": crs
    })
    
    process_json = json.dumps(process_pipeline)
    
    try:
        success, err_msg = execute_with_memory_limit(['pdal', 'pipeline', '-s'], process_json.encode('utf-8'), memory_limit_mb=1536)
        if not success:
            if "0 points" not in err_msg.lower() and "empty" not in err_msg.lower():
                logger.error(f"PDAL core pipeline failed: {err_msg}")
        return True
    except MemoryError as e:
        logger.warning(f"OOM triggered for {out_path.name}: {e}. Initiating recursive dynamic sub-tiling.")
        
        # Calculate 4 new core_polys
        c_minx, c_miny, c_maxx, c_maxy = core_poly.bounds
        
        # Base case: do not recurse if the tile is already tiny (e.g. < 32 meters)
        if (c_maxx - c_minx) < 32 or (c_maxy - c_miny) < 32:
            logger.error(f"Tile {out_path.name} is too small to split further (width/height < 32m). Aborting recursion.")
            return False
            
        midx = (c_minx + c_maxx) / 2
        midy = (c_miny + c_maxy) / 2
        
        quads = [
            box(c_minx, c_miny, midx, midy),
            box(midx, c_miny, c_maxx, midy),
            box(c_minx, midy, midx, c_maxy),
            box(midx, midy, c_maxx, c_maxy)
        ]
        
        b_minx, b_miny, b_maxx, b_maxy = buffered_poly.bounds
        buffer_dist_x = c_minx - b_minx
        buffer_dist_y = c_miny - b_miny
        
        sub_files = []
        for i, q_core in enumerate(quads):
            qm_minx, qm_miny, qm_maxx, qm_maxy = q_core.bounds
            q_buf = box(qm_minx - buffer_dist_x, qm_miny - buffer_dist_y, 
                        qm_maxx + buffer_dist_x, qm_maxy + buffer_dist_y)
            q_out = out_path.with_name(f"{out_path.stem}_sub{i}.laz")
            
            # Recursive Call!
            success = run_pdal_standardization(raw_index_path, q_out, crs, q_core, q_buf, provider, grid_crs, classifier, point_density)
            if success and q_out.exists():
                sub_files.append(q_out)
            elif not success:
                logger.error(f"Sub-quadrant {i} failed recursively.")
                return False
                
        if not sub_files:
            return True # All were empty organically
            
        logger.info(f"Merging {len(sub_files)} sub-quadrants back into {out_path.name}")
        merge_pipeline = []
        inputs = []
        for i, f in enumerate(sub_files):
            tag = f"sub_{i}"
            merge_pipeline.append({"type": "readers.las", "filename": str(f.absolute()), "tag": tag})
            inputs.append(tag)
        
        merge_pipeline.append({"type": "filters.merge", "inputs": inputs})
        merge_pipeline.append({
            "type": "writers.las", 
            "filename": str(out_path.absolute()), 
            "compression": "laszip",
            "a_srs": crs
        })
        
        subprocess.run(['pdal', 'pipeline', '-s'], input=json.dumps(merge_pipeline).encode('utf-8'), check=True)
        
        for f in sub_files:
            f.unlink()
            
        return True
    except Exception as e:
        logger.error(f"Unexpected error in pipeline: {e}")
        return False

def run_final_copc_merge(interim_index_path: Path, final_copc_path: Path, crs: str, workers: int = 1) -> bool:
    """
    Executes a single pipeline reading from the interim tindex and writing directly to COPC.
    """
    final_copc_path.parent.mkdir(parents=True, exist_ok=True)
    
    pipeline = [
        {
            "type": "readers.tindex",
            "filename": str(interim_index_path.absolute()),
            "t_srs": crs
        },
        {
            "type": "writers.copc",
            "filename": str(final_copc_path.absolute()),
            "forward": "all",
            "threads": workers,
            "a_srs": crs
        }
    ]
    
    pdal_json = json.dumps(pipeline)
    
    try:
        subprocess.run(['pdal', 'pipeline', '-s'], input=pdal_json.encode('utf-8'), capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Final COPC merge failed: {e.stderr.decode('utf-8')}")
        return False
    except Exception as e:
        logger.error(f"Final COPC merge failed: {e}")
        return False
