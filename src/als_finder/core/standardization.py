import logging
import json
import os
from pathlib import Path
from typing import Optional, List
from shapely.geometry import Polygon

logger = logging.getLogger(__name__)

def run_pdal_standardization(
    input_path: Path, 
    crs: str, 
    roi_poly: Optional[Polygon] = None, 
    provider: str = 'UNKNOWN'
) -> Optional[Path]:
    """
    Constructs and executes a PDAL pipeline to standardize the LiDAR payload natively.
    Applies reprojection, ASPRS classification standardization, and ROI cropping.
    
    Args:
        input_path: The local path to the raw .laz file
        crs: Target output CRS (e.g., 'EPSG:5070')
        roi_poly: Optional Shapely polygon to crop the bounds to
        provider: Original provider to determine classification mapping logic
    
    Returns:
        Path to the newly normalized .laz file, or None if failed.
    """
    # Dynamically structuralize routing
    raw_parent = str(input_path.parent)
    standardized_parent = Path(raw_parent.replace('data/raw', 'data/standardized'))
    standardized_parent.mkdir(parents=True, exist_ok=True)
    out_path = standardized_parent / f"{input_path.stem}.copc.laz"
    
    pipeline = [
        str(input_path.absolute())
    ]
    
    # 1. Reprojection filter
    if crs:
        # Dynamically intercept UTM requests
        target_crs = crs
        if crs.lower() == 'auto-utm':
            if roi_poly:
                import math
                centroid = roi_poly.centroid
                lon, lat = centroid.x, centroid.y
                zone = math.floor((lon + 180) / 6.0) + 1
                epsg = 32600 + zone if lat >= 0 else 32700 + zone
                target_crs = f"EPSG:{epsg}"
                logger.info(f"Dynamically mapped auto-utm to local zone: {target_crs}")
            else:
                logger.warning("auto-utm requested but no ROI supplied. Falling back to EPSG:3857")
                target_crs = "EPSG:3857"
                
        # Standardize strictly into meters using the target explicitly
        pipeline.append({
            "type": "filters.reprojection",
            "out_srs": target_crs
        })
        
    # 2. (Skipped) Crop geometrically - Removed to keep the 50m buffer intact per Issue #9
        
    # 3. Density-Agnostic Noise Filtering (Issue #9)
    # First, respect any vendor noise classifications (7=Low, 18=High) before wiping
    pipeline.append({
        "type": "filters.expression",
        "expression": "Classification != 7 && Classification != 18"
    })
    
    # Second, run a robust statistical outlier filter for unclassified ghost points natively
    pipeline.append({
        "type": "filters.outlier",
        "method": "statistical",
        "mean_k": 12,
        "multiplier": 3.0
    })
    
    # 4. Scientific Taxonomy Overwrite & Morphological Surface Generation natively natively over local grids
    pipeline.append({
        "type": "filters.assign",
        "assignment": "Classification[:]=1"  # Force wipe structural metadata to Unclassified
    })
    
    # SMRF explicitly requires valid return numbers to operate. Filter out invalid 0s to prevent pipeline crashes.
    pipeline.append({
        "type": "filters.expression",
        "expression": "ReturnNumber > 0 && NumberOfReturns > 0"
    })
    
    pipeline.append({
        "type": "filters.smrf" # SMRF maps the mathematical ground surface to ASPRS Class 2
    })
        
    # Target Writer (COPC: Cloud Optimized Point Cloud)
    pipeline.append({
        "type": "writers.copc",
        "filename": str(out_path.absolute()),
        "forward": "all"
    })
    
    pdal_json = json.dumps(pipeline)
    
    try:
        import pdal
        logger.info(f"Executing standard python-pdal Standardization on {input_path.name} -> {target_crs}")
        p = pdal.Pipeline(pdal_json)
        p.execute()
        return out_path
    except ImportError:
        logger.warning("'python-pdal' not found natively; falling back directly to global PDAL CLI execution.")
        import subprocess
        try:
            res = subprocess.run(['pdal', 'pipeline', '-s'], input=pdal_json.encode('utf-8'), capture_output=True, check=True)
            logger.info(f"Successfully executed native PDAL pipeline on {input_path.name} -> {target_crs}")
            return out_path
        except FileNotFoundError:
            logger.error("Critical Error: 'pdal' command not found globally or in Conda. Please install pdal to use standardization.")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"PDAL Pipeline execution failed natively for {input_path.name}: {e.stderr.decode('utf-8')}")
            return None
    except Exception as e:
        logger.error(f"PDAL Pipeline execution failed natively for {input_path.name}: {e}")
        return None
