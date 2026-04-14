import logging
import json
import os
from pathlib import Path
from typing import Optional, List
from shapely.geometry import Polygon

logger = logging.getLogger(__name__)

def run_pdal_normalization(
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
    try:
        import pdal
    except ImportError:
        logger.error("Critical Error: 'pdal' or 'python-pdal' not found in environment. Please install pdal to use normalization.")
        return None
        
    out_path = input_path.parent / f"{input_path.stem}_norm.copc.laz"
    
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
        
    # 2. Classification Harmonization (Placeholder for robust taxonomy mapping)
    # E.g. if some provider uses 11 for ground, we map it to 2 per standard ASPRS.
    if provider.upper() == 'NOAA_STAC':
        # NOAA is typically decent, but example of how we could filter:
        # pipeline.append({
        #     "type": "filters.assign",
        #     "assignment": "Classification[:]=2 WHERE Classification == 11"
        # })
        pass
        
    # 3. Crop geometrically if a polygon was physically declared
    if roi_poly:
        pipeline.append({
            "type": "filters.crop",
            "polygon": roi_poly.wkt
        })
        
    # Target Writer (COPC: Cloud Optimized Point Cloud)
    pipeline.append({
        "type": "writers.copc",
        "filename": str(out_path.absolute()),
        "forward": "all"
    })
    
    pdal_json = json.dumps(pipeline)
    
    try:
        logger.info(f"Executing PDAL Normalization on {input_path.name} -> {crs}")
        p = pdal.Pipeline(pdal_json)
        p.execute()
        return out_path
    except Exception as e:
        logger.error(f"PDAL Pipeline execution failed natively for {input_path.name}: {e}")
        return None
