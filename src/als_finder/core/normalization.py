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
        
    out_path = input_path.parent / f"{input_path.stem}_norm{input_path.suffix}"
    
    pipeline = [
        str(input_path.absolute())
    ]
    
    # 1. Reprojection filter
    if crs:
        # Standardize strictly into meters using the target explicitly
        pipeline.append({
            "type": "filters.reprojection",
            "out_srs": crs
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
        
    # Target Writer
    pipeline.append({
        "type": "writers.las",
        "filename": str(out_path.absolute()),
        "forward": "all",  # Forward all previous VLRs if possible
        "extra_dims": "all" # Forward extra dimensions unconditionally
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
