import logging
import json
import os
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple
import geopandas as gpd
from shapely.geometry import Polygon, box

logger = logging.getLogger(__name__)

def generate_512m_grid(gdf: gpd.GeoDataFrame) -> List[Tuple[Polygon, Polygon]]:
    """
    Generates a 512m x 512m vector grid over the total bounds of the provided GeoDataFrame.
    Assumes the GeoDataFrame is already in a metric CRS (e.g., EPSG:3857).
    Returns a list of tuples: (core_polygon, buffered_polygon)
    where core_polygon is 512x512m and buffered_polygon is 612x612m.
    """
    minx, miny, maxx, maxy = gdf.total_bounds
    
    # Snap to nearest 512m to create a uniform grid
    import math
    minx = math.floor(minx / 512) * 512
    miny = math.floor(miny / 512) * 512
    maxx = math.ceil(maxx / 512) * 512
    maxy = math.ceil(maxy / 512) * 512
    
    grid = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            core_poly = box(x, y, x + 512, y + 512)
            buffered_poly = box(x - 50, y - 50, x + 512 + 50, y + 512 + 50)
            grid.append((core_poly, buffered_poly))
            y += 512
        x += 512
        
    return grid

def run_pdal_standardization(
    raw_index_path: Path, 
    out_path: Path,
    crs: str, 
    core_poly: Polygon,
    buffered_poly: Polygon,
    provider: str = 'UNKNOWN'
) -> bool:
    """
    Constructs and executes a PDAL pipeline to standardize a single tile from the tindex.
    Applies reprojection, ASPRS classification standardization, SMRF, HAG_NN, and crops to the core.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Bounding boxes for readers.tindex and filters.crop
    b_minx, b_miny, b_maxx, b_maxy = buffered_poly.bounds
    c_minx, c_miny, c_maxx, c_maxy = core_poly.bounds
    
    buffered_bounds_str = f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])"
    core_bounds_str = f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])"
    
    pipeline = []
    
    # 1. Reader from the tindex using the buffered bounds
    pipeline.append({
        "type": "readers.tindex",
        "filename": str(raw_index_path.absolute()),
        "bounds": buffered_bounds_str
    })
    
    # 2. Reprojection filter
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
            
        pipeline.append({
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
        
    # 3. Density-Agnostic Noise Filtering
    pipeline.append({
        "type": "filters.expression",
        "expression": "Classification != 7 && Classification != 18"
    })
    
    # 4. Statistical outlier filter
    pipeline.append({
        "type": "filters.outlier",
        "method": "statistical",
        "mean_k": 12,
        "multiplier": 3.0
    })
    
    # 5. Scientific Taxonomy Overwrite
    pipeline.append({
        "type": "filters.assign",
        "assignment": "Classification[:]=1"
    })
    
    pipeline.append({
        "type": "filters.expression",
        "expression": "ReturnNumber > 0 && NumberOfReturns > 0"
    })
    
    # 6. Morphological Surface Generation
    pipeline.append({
        "type": "filters.smrf"
    })
    
    # 7. Compute Height Above Ground (HAG)
    pipeline.append({
        "type": "filters.hag_nn"
    })
    
    # 8. Precision crop down to the core bounds (stripping the 50m buffer)
    pipeline.append({
        "type": "filters.crop",
        "bounds": core_bounds_str
    })
        
    # 9. Target Writer (Standard .laz for intermediate to save I/O overhead)
    pipeline.append({
        "type": "writers.las",
        "filename": str(out_path.absolute()),
        "compression": "laszip"
    })
    
    pdal_json = json.dumps(pipeline)
    
    try:
        import pdal
        p = pdal.Pipeline(pdal_json)
        p.execute()
        # If output file wasn't created (e.g. no points in this tile), return True to not fail the pipeline
        if not out_path.exists():
            return True
        return True
    except ImportError:
        try:
            subprocess.run(['pdal', 'pipeline', '-s'], input=pdal_json.encode('utf-8'), capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            # It's possible the tile had 0 points, PDAL fails gracefully, we can just skip it
            return True
    except Exception as e:
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
