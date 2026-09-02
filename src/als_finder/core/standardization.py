import logging
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Union, List, Optional, Tuple, Dict, Any
import geopandas as gpd
from shapely.geometry import Polygon, box

logger = logging.getLogger(__name__)

def execute_with_memory_limit(cmd: List[str], input_data: bytes, memory_limit_mb: int = 4096) -> Tuple[bool, str]:
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

def detect_classification_presence(file_path: Path) -> bool:
    """
    Memory-safe probe to detect if Class 2 (Ground) points exist in a LAS/LAZ file.
    Returns True if ground classifications exist, False otherwise.
    """
    import laspy
    try:
        with laspy.open(str(file_path)) as fh:
            for points in fh.chunk_iterator(100000):
                classes = points.classification
                if 2 in classes:
                    return True
    except Exception as e:
        logger.warning(f"Classification probe failed for {file_path.name}: {e}")
    return False

def run_pdal_standardization(
    raw_index_path: Path, 
    out_path: Path,
    crs: str, 
    core_poly: Polygon,
    buffered_poly: Polygon,
    provider: str = 'UNKNOWN',
    grid_crs: str = 'EPSG:3857',
    classifier: str = 'smrf',
    point_density: float = None,
    csf_resolution: float = 1.0,
    csf_step: float = 0.5,
    normal_threshold_z: float = 0.85,
    force_noise_filter: bool = False
) -> bool:
    """
    Constructs and executes a PDAL pipeline to standardize a single tile from the tindex.
    Applies reprojection, ASPRS classification standardization, SMRF, HAG_NN, and crops to the core.

    Args:
        raw_index_path: Path to the raw GeoPackage index.
        out_path: Path to write the standardized output tile.
        crs: Target CRS for the output data.
        core_poly: Geometry of the core tile bounds.
        buffered_poly: Geometry of the buffered tile bounds.
        provider: Provider name.
        grid_crs: CRS for the orchestration grid.
        classifier: Ground classification algorithm to use.
        point_density: Estimated point density.
        csf_resolution: Resolution parameter for CSF cloth.
        csf_step: Step size parameter for CSF cloth.
        normal_threshold_z: NormalZ threshold to filter sloped natural terrain.

    Returns:
        bool: True if successful, False otherwise.
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
                
            # CRITICAL FIX: The downloaded file is the entire subset. 
            # We must crop it down to the buffered_poly immediately before heavy math.
            b_minx, b_miny, b_maxx, b_maxy = buffered_poly.bounds
            process_pipeline.append({
                "type": "filters.crop",
                "bounds": f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])",
                "a_srs": "EPSG:3857"
            })
    except Exception as e:
        logger.error(f"Failed to instantiate provider or build reader: {e}")
        return False
    
    # 3. Reprojection filter (from native CRS)
    # If the user specified a specific CRS (like a Centroid UTM), project to it before math.
    # If 'native', we skip this and process in the provider's native projection.
    if crs and crs != 'native':
        process_pipeline.append({
            "type": "filters.reprojection",
            "out_srs": crs
        })
        
    core_bounds_str = f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])"
        
    # 4. Scientific Taxonomy Overwrite
    if classifier == 'vendor':
        # Reset all non-ground (Class 2) and non-noise (Class 7/18) classifications to Class 1 (Unclassified)
        process_pipeline.append({
            "type": "filters.assign",
            "value": [
                "Classification = 1 WHERE (Classification != 2 && Classification != 7 && Classification != 18)"
            ]
        })
    else:
        process_pipeline.append({
            "type": "filters.assign",
            "assignment": "Classification[:]=1"
        })
    
    # 5. Drop Invalid Returns
    process_pipeline.append({
        "type": "filters.expression",
        "expression": "ReturnNumber > 0 && NumberOfReturns > 0"
    })
    
    if classifier != 'vendor' or force_noise_filter:
        # 6. Extended Local Minimum (ELM) Filter for low noise
        process_pipeline.append({
            "type": "filters.elm",
            "cell": 20.0,
            "threshold": 1.5,
            "class": 7
        })
        
        # 7. Statistical outlier filter for high noise
        process_pipeline.append({
            "type": "filters.outlier",
            "method": "statistical",
            "mean_k": 12,
            "multiplier": 2.2,
            "class": 7
        })
    # 7. Dynamic Ground Classification
    if classifier not in ['none', 'vendor']:
        # Dynamic density scaling for SMRF parameters
        if point_density is None or point_density >= 5.0:
            cell_size = 1.0
            window_size = 18.0  # Fast, detailed for high-density
        elif point_density >= 1.0:
            cell_size = 2.0
            window_size = 33.0  # Balanced search range
        else:
            cell_size = 3.0
            window_size = 65.0  # Wide search for sparse points
            
        if classifier == 'smrf':
            process_pipeline.append({
                "type": "filters.smrf",
                "ignore": "Classification[7:7]",
                "cell": cell_size,
                "window": window_size,
                "slope": 0.5,
                "threshold": 0.5,
                "scalar": 1.25
            })
        elif classifier == 'csf':
            process_pipeline.append({
                "type": "filters.csf",
                "resolution": csf_resolution,
                "step": csf_step
            })
        elif classifier == 'hybrid-dual':
            # Pass 1: Macro CSF (Structure Removal - "Iron Board")
            # If csf_resolution is 1.0 (default CLI value), we default macro_resolution to 3.0 for hybrid-dual.
            # Otherwise, we respect the custom csf_resolution specified by the user.
            macro_resolution = csf_resolution if csf_resolution != 1.0 else 3.0
            process_pipeline.append({
                "type": "filters.csf",
                "resolution": macro_resolution,
                "step": 0.5,
                "rigidness": 3,
                "ignore": "Classification[7:7]"
            })
            # State Saving: Macro HAG Calculation
            process_pipeline.append({
                "type": "filters.hag_nn"
            })
            # Pass 2: Micro SMRF (Terrain Detail - "Dune Protector")
            process_pipeline.append({
                "type": "filters.smrf",
                "ignore": "Classification[7:7]",
                "cell": cell_size,
                "window": 18.0,
                "slope": 0.80,
                "threshold": 0.6,
                "scalar": 1.50
            })
            # The Recombination Logic
            if normal_threshold_z > 0.0:
                process_pipeline.append({
                    "type": "filters.normal",
                    "knn": 8
                })
                process_pipeline.append({
                    "type": "filters.assign",
                    "value": f"Classification = 1 WHERE HeightAboveGround > 4.0 && NormalZ > {normal_threshold_z} && Classification == 2"
                })
            else:
                process_pipeline.append({
                    "type": "filters.assign",
                    "value": "Classification = 1 WHERE HeightAboveGround > 4.0 && Classification == 2"
                })
    
    # 8. Clean up noise points (Drop)
    process_pipeline.append({
        "type": "filters.expression",
        "expression": "Classification != 7 && Classification != 18"
    })
    
    # 9. Compute standard HAG for the final user export
    process_pipeline.append({
        "type": "filters.hag_nn"
    })
    
    # 10. Global Fusion: Reproject back to EPSG:3857 (Web Mercator) for COPC
    process_pipeline.append({
        "type": "filters.reprojection",
        "out_srs": "EPSG:3857"
    })
    
    # 11. Precision crop down to the core bounds (stripping the buffer in 3857 space)
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
    
    process_json = json.dumps(process_pipeline, indent=4)
    
    # DEBUG: Dump the pipeline to a file
    try:
        with open("scratch/debug_pipeline.json", "w") as f:
            f.write(process_json)
    except Exception:
        pass
    
    import time
    start_t = time.time()
    try:
        success, err_msg = execute_with_memory_limit(['pdal', 'pipeline', '-s'], process_json.encode('utf-8'), memory_limit_mb=1536)
        end_t = time.time()
        
        if not success:
            if "0 points" not in err_msg.lower() and "empty" not in err_msg.lower():
                logger.error(f"PDAL core pipeline failed: {err_msg}")
        else:
            c_width = c_maxx - c_minx
            c_height = c_maxy - c_miny
            exec_time = end_t - start_t
            area = c_width * c_height
            time_per_m2 = exec_time / area if area > 0 else 0.0
            logger.info(f"Tile Execution Success ({c_width:.0f}x{c_height:.0f}m) in {exec_time:.2f}s ({time_per_m2:.6f} s/m²)")
            
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
            success = run_pdal_standardization(
                raw_index_path, 
                q_out, 
                crs, 
                q_core, 
                q_buf, 
                provider, 
                grid_crs, 
                classifier, 
                point_density, 
                csf_resolution, 
                csf_step,
                normal_threshold_z,
                force_noise_filter
            )
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
    
    json_str = json.dumps(pipeline, indent=4)
    
    # DEBUG: Dump the pipeline to a file
    try:
        with open("scratch/debug_pipeline.json", "w") as f:
            f.write(json_str)
    except Exception:
        pass
        
    try:
        process = subprocess.run(
            ['pdal', 'pipeline', '-s'],
            input=json_str.encode('utf-8'), capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Final COPC merge failed: {e.stderr.decode('utf-8')}")
        return False
    except Exception as e:
        logger.error(f"Final COPC merge failed: {e}")
        return False

def stream_single_tile(
    manifest_or_grid_path: Union[str, Path],
    tile_id: Union[int, str] = 0,
    out_path: Optional[Union[str, Path]] = None,
    tile_size: int = 1200,
    buffer_size: int = 30,
    crs: str = "EPSG:3857",
    overwrite: bool = False,
    use_spatial_name: bool = False,
    write_sidecar: bool = False,
) -> Path:
    """
    Directly streams and crops point cloud data for a single spatial tile into a standardized .laz file.
    Supports integer base tile IDs (e.g. 15) and hierarchical quadrant string IDs (e.g. '15_NW').
    Automatically nests output within a Hive-partitioned directory layout if out_path is a directory or None.

    Args:
        manifest_or_grid_path (Union[str, Path]): Path to catalog manifest.json, workspace dir, or grid.gpkg.
        tile_id (Union[int, str]): Target tile index or quadrant string (e.g. 15 or '15_NW').
        out_path (Optional[Union[str, Path]]): Destination file or directory path. If a directory
            (e.g. /scratch or workspace/data), automatically nests output within Hive partition hierarchy.
        tile_size (int): Core metric tile size in meters (default: 1200m).
        buffer_size (int): Overlap buffer size in meters (default: 30m).
        crs (str): Target coordinate reference system (default: EPSG:3857).
        overwrite (bool): Force re-creation if output tile already exists.
        use_spatial_name (bool): If True, uses metric coordinate-anchored filename.
        write_sidecar (bool): If True, writes a companion .json sidecar metadata file alongside the .laz tile.

    Returns:
        Path: Path to the generated .laz tile.
    """
    from als_finder.core.grid_manager import get_tile_spec
    from als_finder.providers import get_provider

    # 1. Retrieve tile spec via zero-copy SQL query (lazy auto-builds grid if missing or overwrite=True!)
    spec = get_tile_spec(
        manifest_or_grid_path,
        tile_id,
        tile_size=tile_size,
        buffer_size=buffer_size,
        overwrite=overwrite
    )
    buffered_poly = spec["buffered_poly"]
    urls = spec["urls"]

    if not urls:
        raise ValueError(f"No dataset URLs found in manifest/grid for tile_id {tile_id}")

    rel_hive = spec["hive_path"]
    rel_file = f"{rel_hive}.laz" if not rel_hive.endswith(".laz") else rel_hive

    # 2. Resolve output path: if directory or None, append Hive partition hierarchy
    if out_path is None:
        p = Path(manifest_or_grid_path)
        ws_dir = p.parent.parent if p.parent.name == "catalog" else (p if p.is_dir() else p.parent)
        target_out = ws_dir / "data" / "tiles" / rel_file
    else:
        raw_out = Path(out_path)
        if raw_out.is_dir() or raw_out.suffix.lower() != ".laz":
            target_out = raw_out / rel_file
        else:
            target_out = raw_out

    if target_out.exists() and not overwrite:
        logger.info(f"Tile output {target_out} already exists and overwrite=False. Skipping.")
        return target_out

    target_out.parent.mkdir(parents=True, exist_ok=True)

    pipeline = []

    # 2. Build provider reader stages
    if str(urls[0]).startswith("http"):
        provider_name = spec.get("provider", "USGS_EPT")
        provider_instance = get_provider(provider_name)
        poly_crs = spec.get("grid_crs", "EPSG:4326")
        reader_stages = provider_instance.get_pdal_reader(urls, buffered_poly, poly_crs=poly_crs)
        pipeline.extend(reader_stages)
    else:
        inputs = []
        for i, url in enumerate(urls):
            tag = f"reader_{i}"
            reader_type = "readers.copc" if str(url).lower().endswith(".copc.laz") else "readers.las"
            pipeline.append({"type": reader_type, "filename": str(url), "tag": tag})
            inputs.append(tag)
        if len(urls) > 1:
            pipeline.append({"type": "filters.merge", "inputs": inputs})

    grid_crs = spec.get("grid_crs", "EPSG:32610")
    # Default target_crs to grid_crs (projected UTM) for metric accuracy unless explicitly overridden
    target_crs = crs if (crs and crs != "EPSG:3857") else grid_crs

    # 3. Reprojection to target CRS so crop bounds match point cloud coordinate space
    if target_crs and target_crs.lower() != "native":
        pipeline.append({
            "type": "filters.reprojection",
            "out_srs": target_crs,
        })

    # 4. Transform buffered_poly to target_crs so crop bounds match point cloud coordinates exactly
    from pyproj import Transformer
    from shapely.ops import transform
    if target_crs and grid_crs and target_crs != grid_crs:
        transformer = Transformer.from_crs(grid_crs, target_crs, always_xy=True)
        crop_poly = transform(transformer.transform, buffered_poly)
    else:
        crop_poly = buffered_poly

    b_minx, b_miny, b_maxx, b_maxy = crop_poly.bounds
    pipeline.append({
        "type": "filters.crop",
        "bounds": f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])",
    })

    # 5. Taxonomy assignment & expression filter
    pipeline.append({
        "type": "filters.assign",
        "value": ["Classification = 1 WHERE (Classification != 2 && Classification != 7 && Classification != 18)"],
    })
    pipeline.append({
        "type": "filters.expression",
        "expression": "ReturnNumber > 0 && NumberOfReturns > 0",
    })

    # 6. Writer stage
    pipeline.append({
        "type": "writers.las",
        "filename": str(target_out.absolute()),
        "compression": "laszip",
        "a_srs": target_crs,
    })

    # 7. Memory-guarded PDAL execution
    pdal_json = json.dumps(pipeline)
    success, err_msg = execute_with_memory_limit(
        ["pdal", "pipeline", "-s"],
        pdal_json.encode("utf-8"),
        memory_limit_mb=4096,
    )

    if not success or not target_out.exists():
        raise RuntimeError(f"PDAL stream execution failed for tile_id {tile_id}: {err_msg}")

    # 8. Optional sidecar metadata export
    if write_sidecar:
        sidecar_path = target_out.with_suffix(".json")
        core_b = spec["core_poly"].bounds
        buf_b = spec["buffered_poly"].bounds
        sidecar_meta = {
            "tile_id": str(tile_id) if spec.get("quadrant") else int(spec.get("parent_tile_id", tile_id)),
            "parent_tile_id": spec.get("parent_tile_id"),
            "quadrant": spec.get("quadrant"),
            "level": spec.get("level", 0),
            "basename": spec.get("basename", target_out.stem),
            "hive_dir": spec.get("hive_dir"),
            "hive_path": spec.get("hive_path"),
            "path": str(target_out.absolute()),
            "dataset_id": str(spec.get("dataset_id", "")),
            "provider": str(spec.get("provider", "")),
            "grid_crs": str(target_crs),
            "tile_size": int(spec.get("tile_size", tile_size)),
            "buffer_size": int(spec.get("buffer_size", buffer_size)),
            "est_points": spec.get("est_points"),
            "is_hyperdense": spec.get("is_hyperdense", False),
            "recommended_mem_gb": spec.get("recommended_mem_gb"),
            "core_bounds": spec.get("crop_bbox", [round(core_b[0], 2), round(core_b[1], 2), round(core_b[2], 2), round(core_b[3], 2)]),
            "crop_pdal_bounds": spec.get("crop_pdal_bounds"),
            "crop_gdal_te": spec.get("crop_gdal_te"),
            "buffered_bounds": [round(buf_b[0], 2), round(buf_b[1], 2), round(buf_b[2], 2), round(buf_b[3], 2)],
            "source_urls": spec.get("urls", []),
        }
        with open(sidecar_path, "w", encoding="utf-8") as sf:
            json.dump(sidecar_meta, sf, indent=2)
        logger.info(f"Wrote metadata sidecar to {sidecar_path}")

    return target_out
