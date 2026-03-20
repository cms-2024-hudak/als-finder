from pathlib import Path
from typing import Union, List, Optional, Tuple
import geopandas as gpd
from shapely.geometry import box, Polygon, MultiPolygon
from shapely.ops import unary_union
import json
import logging

logger = logging.getLogger(__name__)

class ROIError(Exception):
    """Custom exception for ROI processing errors."""
    pass

def load_roi(source: Union[str, Path, List[float]]) -> Polygon:
    """
    Load a Region of Interest (ROI) from a file or bounding box.

    Args:
        source: 
            - Path to a file (GeoJSON, Shapefile, etc. supported by geopandas/fiona).
            - List/Tuple of floats representing BBox: [min_x, min_y, max_x, max_y].
            - Comma-separated string of BBox: "min_x,min_y,max_x,max_y".

    Returns:
        shapely.geometry.Polygon: A single Polygon (or MultiPolygon) representing the ROI 
        in EPSG:4326 (WGS84).
    """
    try:
        # 1. Handle BBox as list/tuple
        if isinstance(source, (list, tuple)):
            if len(source) != 4:
                raise ROIError(f"BBox list must have 4 elements [minx, miny, maxx, maxy], got {len(source)}")
            return _bbox_to_polygon(source)

        # 2. Handle BBox as string
        if isinstance(source, str):
            # Check if it looks like a list of numbers
            if "," in source and source.replace(",", "").replace(".", "").replace("-", "").replace(" ", "").isdigit():
                 try:
                     parts = [float(x.strip()) for x in source.split(",")]
                     if len(parts) == 4:
                         return _bbox_to_polygon(parts)
                 except ValueError:
                     pass # Not a simple bbox string, treat as file path

            # 3. Handle File Path
            path = Path(source)
            if not path.exists():
                raise ROIError(f"ROI file not found: {path}")

            gdf = gpd.read_file(path)
            
            if gdf.empty:
                raise ROIError("ROI file is empty.")

            # Reproject to WGS84 if needed
            if gdf.crs is None:
                logger.warning("ROI file has no CRS defined. Assuming EPSG:4326.")
                gdf.set_crs(epsg=4326, inplace=True)
            elif gdf.crs.to_string() != "EPSG:4326":
                logger.info(f"Reprojecting ROI from {gdf.crs.to_string()} to EPSG:4326")
                gdf = gdf.to_crs(epsg=4326)

            # Dissolve to a single geometry
            geom = unary_union(gdf.geometry)
            
            if isinstance(geom, (Polygon, MultiPolygon)):
                return geom
            else:
                # Handle cases like GeometryCollection
                raise ROIError(f"Resulting geometry is {type(geom)}, expected Polygon or MultiPolygon.")

    except Exception as e:
        logger.error(f"Failed to load ROI: {e}")
        raise ROIError(f"Failed to load ROI: {e}") 

def _bbox_to_polygon(bbox: Union[List[float], Tuple[float, ...]]) -> Polygon:
    """Convert [minx, miny, maxx, maxy] to a Polygon in EPSG:4326."""
    minx, miny, maxx, maxy = bbox
    # Basic validation
    if minx >= maxx or miny >= maxy:
         raise ROIError(f"Invalid BBox dimensions: {bbox}. Min must be less than Max.")
    
    return box(minx, miny, maxx, maxy)

def validate_roi(geom: Polygon) -> bool:
    """Basic validation checks for an ROI polygon."""
    if not geom.is_valid:
        return False
    # Check bounds (WGS84)
    minx, miny, maxx, maxy = geom.bounds
    if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        logger.warning(f"ROI bounds {geom.bounds} appear outside valid WGS84 range.")
    return True
