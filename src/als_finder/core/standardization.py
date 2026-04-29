import logging
import json
import os
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple
import geopandas as gpd
from shapely.geometry import Polygon, box

logger = logging.getLogger(__name__)

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
    grid_crs: str = 'EPSG:3857'
) -> bool:
    """
    Constructs and executes a PDAL pipeline to standardize a single tile from the tindex.
    Applies reprojection, ASPRS classification standardization, SMRF, HAG_NN, and crops to the core.
    """
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
    
    # 7. Morphological Surface Generation
    process_pipeline.append({
        "type": "filters.smrf"
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
        "compression": "laszip"
    })
    
    process_json = json.dumps(process_pipeline)
    
    try:
        try:
            import pdal
            p = pdal.Pipeline(process_json)
            p.execute()
        except ImportError:
            subprocess.run(['pdal', 'pipeline', '-s'], input=process_json.encode('utf-8'), capture_output=True, check=True)
            
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8')
        if "0 points" not in err_msg.lower() and "empty" not in err_msg.lower():
            logger.error(f"PDAL core pipeline failed: {err_msg}")
        return True
    except Exception as e:
        logger.error(f"Unexpected error in pipeline: {e}")
        return False

def run_final_copc_merge(interim_index_path: Path, final_copc_path: Path) -> bool:
    """
    Executes a single pipeline reading from the interim tindex and writing directly to COPC.
    """
    final_copc_path.parent.mkdir(parents=True, exist_ok=True)
    
    pipeline = [
        {
            "type": "readers.tindex",
            "filename": str(interim_index_path.absolute())
        },
        {
            "type": "writers.copc",
            "filename": str(final_copc_path.absolute()),
            "forward": "all"
        }
    ]
    
    pdal_json = json.dumps(pipeline)
    
    try:
        import pdal
        p = pdal.Pipeline(pdal_json)
        p.execute()
        return True
    except ImportError:
        try:
            subprocess.run(['pdal', 'pipeline', '-s'], input=pdal_json.encode('utf-8'), capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Final COPC merge failed: {e.stderr.decode('utf-8')}")
            return False
    except Exception as e:
        logger.error(f"Final COPC merge failed: {e}")
        return False
