"""
Grid and Tile Management Module for ALS-Finder.

Handles projected metric vector grid tile generation, tile index export (GeoPackage/JSON),
and zero-copy single-row spatial tile specification lookups.
"""

import gc
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import Polygon, box


logger = logging.getLogger(__name__)


class GridError(Exception):
    """Custom exception for grid processing errors."""
    pass


def resolve_projected_crs(
    gdf: gpd.GeoDataFrame,
    target_crs: Optional[str] = None
) -> str:
    """
    Detects or validates the target projected metric CRS for spatial grid slicing.
    
    If target_crs is provided (and not 'auto'), validates and returns it.
    If target_crs is None or 'auto', attempts to estimate the local UTM CRS.
    Fallbacks to EPSG:3857 (Web Mercator) if estimation fails or inputs are unprojected.

    Args:
        gdf (gpd.GeoDataFrame): Input geometry layer.
        target_crs (Optional[str]): Explicit EPSG code or CRS string.

    Returns:
        str: Resolved metric projected CRS string (e.g. "EPSG:32610" or "EPSG:3857").
    """
    if gdf is None or gdf.empty:
        raise GridError("Input GeoDataFrame is empty or None.")

    # 1. User provided an explicit target CRS
    if target_crs and target_crs.lower() != "auto":
        try:
            # Validate CRS string via PyProj/GeoPandas
            test_gdf = gdf.to_crs(target_crs) if gdf.crs else gdf.set_crs(target_crs)
            return test_gdf.crs.to_string()
        except Exception as e:
            logger.warning(f"Failed to validate user-specified target_crs '{target_crs}': {e}. Falling back to auto-detection.")

    # 2. Auto-detect UTM CRS
    # Ensure input has a CRS; if None, assume EPSG:4326 WGS84
    working_gdf = gdf.copy()
    if working_gdf.crs is None:
        logger.warning("Input GeoDataFrame has no CRS. Assuming EPSG:4326 for UTM estimation.")
        working_gdf.set_crs(epsg=4326, inplace=True)

    try:
        # Estimate local UTM zone
        estimated_crs = working_gdf.estimate_utm_crs()
        if estimated_crs:
            crs_str = estimated_crs.to_string()
            logger.info(f"Auto-detected local UTM CRS: {crs_str}")
            return crs_str
    except Exception as e:
        logger.warning(f"UTM CRS estimation failed: {e}. Falling back to EPSG:3857.")

    return "EPSG:3857"


def create_tile_grid_index(
    gdf: gpd.GeoDataFrame,
    tile_size: int = 512,
    buffer_size: int = 50,
    target_crs: Optional[str] = None
) -> Tuple[gpd.GeoDataFrame, str]:
    """
    Generates a uniform vector grid over the total bounds of the GeoDataFrame.
    Snaps bounds to the nearest tile_size step in projected metric space.
    Stores core tile polygons in the primary 'geometry' column and buffered tile polygons
    in a secondary 'buffered_geometry' column.

    Args:
        gdf (gpd.GeoDataFrame): Input ROI spatial layer.
        tile_size (int): Core tile size in meters (default: 512m).
        buffer_size (int): Overlap buffer in meters (default: 50m).
        target_crs (Optional[str]): Explicit target metric CRS or None for auto-detection.

    Returns:
        Tuple[gpd.GeoDataFrame, str]: (grid_gdf, resolved_crs_string)
    """
    if gdf is None or gdf.empty:
        raise GridError("Input GeoDataFrame is empty or None.")

    if tile_size <= 0:
        raise GridError(f"tile_size must be a positive integer > 0, got {tile_size}")

    if buffer_size < 0:
        raise GridError(f"buffer_size cannot be negative, got {buffer_size}")

    if buffer_size > (tile_size / 2) and tile_size > 0:
        logger.warning(
            f"Buffer size ({buffer_size}m) is larger than half core tile size ({tile_size}m). "
            "High buffer overlap ratio may increase byte-fetch redundancy."
        )

    # Resolve metric projection
    grid_crs = resolve_projected_crs(gdf, target_crs=target_crs)
    projected_gdf = gdf.to_crs(grid_crs) if gdf.crs else gdf.set_crs(grid_crs)

    minx, miny, maxx, maxy = projected_gdf.total_bounds
    if math.isnan(minx) or math.isnan(miny) or math.isnan(maxx) or math.isnan(maxy):
        raise GridError("GeoDataFrame total bounds contain NaN values.")

    # Snap bounds to nearest tile_size
    minx = math.floor(minx / tile_size) * tile_size
    miny = math.floor(miny / tile_size) * tile_size
    maxx = math.ceil(maxx / tile_size) * tile_size
    maxy = math.ceil(maxy / tile_size) * tile_size

    core_geoms: List[Polygon] = []
    buffered_geoms: List[Polygon] = []
    tile_ids: List[int] = []

    tile_count = 0
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            core_poly = box(x, y, x + tile_size, y + tile_size)
            buffered_poly = box(
                x - buffer_size,
                y - buffer_size,
                x + tile_size + buffer_size,
                y + tile_size + buffer_size,
            )

            # Spatial intersection filter: keep tiles that intersect the ROI
            if projected_gdf.intersects(buffered_poly).any():
                tile_ids.append(tile_count)
                core_geoms.append(core_poly)
                buffered_geoms.append(buffered_poly)
                tile_count += 1

            y += tile_size
        x += tile_size

    if not core_geoms:
        raise GridError("No grid tiles intersected the input ROI geometry.")

    grid_gdf = gpd.GeoDataFrame(
        {"tile_id": tile_ids, "buffered_geometry": buffered_geoms},
        geometry=core_geoms,
        crs=grid_crs,
    )

    logger.info(f"Generated {len(grid_gdf)} metric tiles in {grid_crs} (tile={tile_size}m, buffer={buffer_size}m)")
    return grid_gdf, grid_crs


def export_grid_manifest(
    grid_gdf: gpd.GeoDataFrame,
    manifest_data: Dict[str, Any],
    output_dir: Path,
    batch_size: int = 5000
) -> Tuple[Path, Path]:
    """
    Exports grid tile index to SQLite/GeoPackage (grid.gpkg) using chunked batch writes
    and updates catalog manifest.json with grid metadata.

    Args:
        grid_gdf (gpd.GeoDataFrame): Grid layer from create_tile_grid_index.
        manifest_data (Dict[str, Any]): Existing catalog manifest dictionary.
        output_dir (Path): Output catalog directory path.
        batch_size (int): Batch size for memory-safe chunked disk writes (default: 5000).

    Returns:
        Tuple[Path, Path]: (grid_gpkg_path, manifest_json_path)
    """
    if grid_gdf is None or grid_gdf.empty:
        raise GridError("Grid GeoDataFrame is empty or None.")

    output_dir.mkdir(parents=True, exist_ok=True)
    gpkg_path = output_dir / "grid.gpkg"
    manifest_path = output_dir / "manifest.json"

    if gpkg_path.exists():
        gpkg_path.unlink()

    # Memory-safe chunked batch writes to GeoPackage
    # Store buffered_geometry as WKT string in GeoPackage table for portability
    export_df = grid_gdf.copy()
    export_df["buffered_wkt"] = export_df["buffered_geometry"].apply(lambda g: g.wkt)
    export_df.drop(columns=["buffered_geometry"], inplace=True)

    num_rows = len(export_df)
    for start_idx in range(0, num_rows, batch_size):
        chunk = export_df.iloc[start_idx : start_idx + batch_size]
        is_append = gpkg_path.exists()
        pyogrio.write_dataframe(chunk, gpkg_path, layer="grid", driver="GPKG", append=is_append)
        del chunk
        gc.collect()

    del export_df
    gc.collect()

    # Update manifest data
    updated_manifest = dict(manifest_data) if manifest_data else {}
    updated_manifest["grid_info"] = {
        "grid_crs": grid_gdf.crs.to_string(),
        "total_tiles": len(grid_gdf),
        "gpkg_file": gpkg_path.name,
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(updated_manifest, f, indent=2)

    logger.info(f"Exported grid index ({len(grid_gdf)} tiles) to {gpkg_path} and {manifest_path}")
    return gpkg_path, manifest_path


def get_tile_spec(
    manifest_or_grid_path: Path,
    tile_id: int
) -> Dict[str, Any]:
    """
    Retrieves the spatial specification for a single tile ID.
    Uses targeted single-row SQL filtering on grid.gpkg for minimal memory footprint (< 0.1 MB RAM).

    Args:
        manifest_or_grid_path (Path): Path to grid.gpkg or catalog manifest.json directory.
        tile_id (int): Target zero-based tile ID.

    Returns:
        Dict[str, Any]: Dictionary containing tile_id, core_poly, buffered_poly, grid_crs, and urls.
    """
    path = Path(manifest_or_grid_path)
    if not path.exists():
        raise GridError(f"Grid or manifest path does not exist: {path}")

    # Determine GPKG path
    if path.is_dir():
        gpkg_path = path / "grid.gpkg"
        manifest_path = path / "manifest.json"
    elif path.name == "manifest.json":
        gpkg_path = path.parent / "grid.gpkg"
        manifest_path = path
    elif path.suffix.lower() == ".gpkg":
        gpkg_path = path
        manifest_path = path.parent / "manifest.json"
    else:
        raise GridError(f"Unsupported manifest or grid path: {path}")

    if not gpkg_path.exists():
        raise GridError(f"Grid GeoPackage file not found: {gpkg_path}")

    # Memory-safe zero-copy single-row SQL query via pyogrio
    sql_query = f"SELECT * FROM grid WHERE tile_id = {tile_id}"
    try:
        single_row_gdf = pyogrio.read_dataframe(gpkg_path, sql=sql_query)
    except Exception as e:
        raise GridError(f"Failed to query tile_id {tile_id} from {gpkg_path}: {e}")

    if single_row_gdf.empty:
        raise GridError(f"Tile ID {tile_id} not found in {gpkg_path}")

    row = single_row_gdf.iloc[0]
    core_poly: Polygon = row.geometry
    grid_crs: str = single_row_gdf.crs.to_string()

    # Recover buffered polygon from WKT column or geometry fallback
    if "buffered_wkt" in row and isinstance(row["buffered_wkt"], str):
        from shapely.wkt import loads as wkt_loads
        buffered_poly = wkt_loads(row["buffered_wkt"])
    else:
        buffered_poly = core_poly

    b_minx, b_miny, b_maxx, b_maxy = buffered_poly.bounds
    bbox_str = f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])"

    # Read urls from manifest if available
    urls: List[str] = []
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as mf:
                m_data = json.load(mf)
                datasets = m_data.get("datasets", m_data.get("features", []))
                for ds in datasets:
                    url = ds.get("url") or ds.get("assets", {}).get("data", {}).get("href")
                    if url:
                        urls.append(url)
        except Exception as e:
            logger.warning(f"Could not parse URLs from manifest {manifest_path}: {e}")

    return {
        "tile_id": int(tile_id),
        "core_poly": core_poly,
        "buffered_poly": buffered_poly,
        "grid_crs": grid_crs,
        "bbox_str": bbox_str,
        "urls": urls,
    }
