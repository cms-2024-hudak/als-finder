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


def format_coord(val: float) -> str:
    """Format geographic coordinate with zero-padding and 'p' for fractional decimals."""
    f_val = float(val)
    if f_val < 0:
        return f"-{abs(int(f_val)):07d}" if f_val.is_integer() else f"-{abs(f_val):07.1f}".replace(".", "p")
    else:
        return f"{int(f_val):07d}" if f_val.is_integer() else f"{f_val:07.1f}".replace(".", "p")


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

    # Advisory check: Warn if input extent spans multiple UTM zones (>6 degrees longitude)
    try:
        wgs_gdf = working_gdf.to_crs("EPSG:4326") if working_gdf.crs.to_string() != "EPSG:4326" else working_gdf
        minx_wgs, _, maxx_wgs, _ = wgs_gdf.total_bounds
        lon_span = abs(maxx_wgs - minx_wgs)
        if lon_span > 6.0:
            logger.warning(
                f"[ADVISORY] Input study area spans {lon_span:.2f}° longitude, crossing multiple UTM zones (>6°). "
                "Projecting a wide continental extent into a single UTM zone introduces scale and coordinate distortion. "
                "For multi-state or continental modeling, consider specifying an equal-area projection such as --crs EPSG:5070 (CONUS Albers)."
            )
    except Exception as e:
        logger.debug(f"Could not calculate longitudinal span: {e}")

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
    tile_size: int = 500,
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
    batch_size: int = 5000,
    tile_size: Optional[float] = None,
    buffer_size: Optional[float] = None
) -> Tuple[Path, Path]:
    """
    Exports grid tile index to SQLite/GeoPackage (grid.gpkg) using chunked batch writes
    and updates catalog manifest.json with grid metadata.

    Args:
        grid_gdf (gpd.GeoDataFrame): Grid layer from create_tile_grid_index.
        manifest_data (Dict[str, Any]): Existing catalog manifest dictionary.
        output_dir (Path): Output catalog directory path.
        batch_size (int): Batch size for memory-safe chunked disk writes (default: 5000).
        tile_size (Optional[float]): Metric tile dimension (meters).
        buffer_size (Optional[float]): Overlap buffer size (meters).

    Returns:
        Tuple[Path, Path]: (grid_gpkg_path, manifest_json_path)
    """
    if grid_gdf is None or grid_gdf.empty:
        raise GridError("Grid GeoDataFrame is empty or None.")

    # Infer from GeoDataFrame attrs if not explicitly passed
    if tile_size is None and hasattr(grid_gdf, "attrs") and "tile_size" in grid_gdf.attrs:
        tile_size = grid_gdf.attrs["tile_size"]
    if buffer_size is None and hasattr(grid_gdf, "attrs") and "buffer_size" in grid_gdf.attrs:
        buffer_size = grid_gdf.attrs["buffer_size"]

    output_dir.mkdir(parents=True, exist_ok=True)
    gpkg_path = output_dir / "grid.gpkg"
    manifest_path = output_dir / "manifest.json"

    if gpkg_path.exists():
        gpkg_path.unlink()

    # Extract dataset metadata from manifest_data if available
    datasets = manifest_data.get("datasets", manifest_data.get("features", [])) if manifest_data else []
    default_ds = datasets[0] if datasets else {}
    provider = str(default_ds.get("provider", "USGS_EPT"))
    dataset_id = str(default_ds.get("dataset_id", default_ds.get("name", "dataset")))
    name_str = str(default_ds.get("name", dataset_id))
    raw_date = str(default_ds.get("date", "2022"))
    year = raw_date[:4] if len(raw_date) >= 4 else "2022"
    state = "CA"
    point_count = default_ds.get("point_count")
    point_density = default_ds.get("point_density")
    area_sqkm = default_ds.get("area_sqkm")
    
    urls: List[str] = []
    for d in datasets:
        u = d.get("url") or d.get("assets", {}).get("data", {}).get("href")
        if u:
            urls.append(u)
    additional_meta = default_ds.get("additional_metadata") or default_ds.get("raw_metadata") or {}

    # Memory-safe chunked batch writes to GeoPackage
    # Store buffered_geometry as WKT string in GeoPackage table for portability
    export_df = grid_gdf.copy()
    export_df["buffered_wkt"] = export_df["buffered_geometry"].apply(lambda g: g.wkt)
    export_df["core_bounds_str"] = export_df.geometry.apply(
        lambda g: f"([{g.bounds[0]}, {g.bounds[2]}], [{g.bounds[1]}, {g.bounds[3]}])"
    )
    export_df["buffered_bounds_str"] = export_df["buffered_geometry"].apply(
        lambda g: f"([{g.bounds[0]}, {g.bounds[2]}], [{g.bounds[1]}, {g.bounds[3]}])"
    )

    t_size = int(tile_size) if tile_size is not None else 1200
    b_size = int(buffer_size) if buffer_size is not None else 30
    export_df["tile_size"] = t_size
    export_df["buffer_size"] = b_size
    export_df["grid_crs"] = grid_gdf.crs.to_string()
    
    # Pure Hive partition hierarchy (without 'tiles/')
    hive_prefix = f"provider={provider}/dataset={dataset_id}/tilesize={t_size}/buffer={b_size}"
    export_df["basename"] = export_df.apply(
        lambda r: f"{dataset_id}_tile_E{format_coord(r.geometry.bounds[0])}_N{format_coord(r.geometry.bounds[3])}",
        axis=1
    )
    export_df["hive_dir"] = hive_prefix
    export_df["hive_path"] = export_df["basename"].apply(lambda bn: f"{hive_prefix}/{bn}")
    export_df["spatial_basename"] = export_df["basename"]
    export_df["spatial_hive_path"] = export_df["hive_path"]
    export_df["provider"] = provider
    export_df["dataset_id"] = dataset_id
    export_df["name"] = name_str
    export_df["date"] = raw_date
    export_df["year"] = year
    export_df["state"] = state
    export_df["point_count"] = point_count if point_count is not None else None
    export_df["point_density"] = float(point_density) if point_density is not None else None
    export_df["area_sqkm"] = float(area_sqkm) if area_sqkm is not None else None
    export_df["source_urls"] = json.dumps(urls)
    export_df["additional_metadata_json"] = json.dumps(additional_meta, default=str)
    
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
    if "grids" not in updated_manifest:
        updated_manifest["grids"] = {}

    rel_gpkg_str = str(gpkg_path.relative_to(output_dir)) if gpkg_path.is_relative_to(output_dir) else gpkg_path.name
    grid_key = f"tilesize={tile_size}_buffer={buffer_size}" if tile_size is not None and buffer_size is not None else "primary"

    updated_manifest["grids"][grid_key] = {
        "tile_size": tile_size,
        "buffer_size": buffer_size,
        "grid_crs": grid_gdf.crs.to_string(),
        "total_tiles": len(grid_gdf),
        "gpkg_file": rel_gpkg_str,
    }
    updated_manifest["grid_info"] = updated_manifest["grids"][grid_key]

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(updated_manifest, f, indent=2)

    logger.info(f"Exported grid index ({len(grid_gdf)} tiles) to {gpkg_path} and {manifest_path}")
    return gpkg_path, manifest_path


def build_workspace_grid(
    workspace_dir: Union[str, Path],
    tile_size: int = 500,
    buffer_size: int = 50,
    target_crs: Optional[str] = None,
    overwrite: bool = False
) -> Tuple[gpd.GeoDataFrame, str]:
    """
    Automatically builds the spatial tile grid index for a workspace directory
    using the search catalog coverage layer (catalog.gpkg) or workspace ROI. Saves grid to Hive partitioned
    directory catalog/grids/tilesize={tile_size}/buffer={buffer_size}/grid.gpkg.

    Args:
        workspace_dir (Union[str, Path]): Path to workspace root directory.
        tile_size (int): Core metric tile size in meters (default: 1200m).
        buffer_size (int): Overlap buffer in meters (default: 30m).
        target_crs (Optional[str]): Explicit target metric CRS or None for auto-detection.
        overwrite (bool): If True, forces regeneration of the grid even if grid.gpkg exists.

    Returns:
        Tuple[gpd.GeoDataFrame, str]: (grid_gdf, resolved_crs_string)
    """
    ws = Path(workspace_dir)
    if ws.name == "manifest.json" or ws.suffix.lower() == ".gpkg":
        ws = ws.parent.parent if ws.parent.name == "catalog" else ws.parent

    hive_grid_dir = ws / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}"
    gpkg_path = hive_grid_dir / "grid.gpkg"
    
    if gpkg_path.exists() and not overwrite:
        logger.info(f"Using existing grid at {gpkg_path} (use overwrite=True to rebuild)")
        existing_gdf = pyogrio.read_dataframe(gpkg_path)
        crs_str = existing_gdf.crs.to_string() if existing_gdf.crs else "EPSG:3857"
        return existing_gdf, crs_str

    catalog_gpkg = ws / "catalog" / "catalog.gpkg"
    manifest_path = ws / "catalog" / "manifest.json"

    if not catalog_gpkg.exists():
        raise GridError(f"Catalog GeoPackage not found at {catalog_gpkg}. Please run search first.")

    manifest_data = {}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

    # Prioritize ROI geometry over raw remote acquisition footprints
    roi_file = None
    if "search_parameters" in manifest_data and manifest_data["search_parameters"].get("roi"):
        candidate_roi = Path(manifest_data["search_parameters"]["roi"])
        if candidate_roi.exists():
            roi_file = candidate_roi
    if roi_file is None:
        for candidate in [ws / "roi.gpkg", ws / "catalog" / "roi.gpkg"]:
            if candidate.exists():
                roi_file = candidate
                break

    if roi_file is not None:
        logger.info(f"Building spatial grid from workspace ROI: {roi_file}")
        source_gdf = gpd.read_file(roi_file)
    else:
        logger.info("No dedicated ROI file found; building spatial grid from catalog footprint.")
        source_gdf = gpd.read_file(catalog_gpkg)

    grid_gdf, crs_str = create_tile_grid_index(
        source_gdf,
        tile_size=tile_size,
        buffer_size=buffer_size,
        target_crs=target_crs
    )
    
    # Extract dataset provenance and additional/rando metadata from manifest or catalog
    datasets = manifest_data.get("datasets", manifest_data.get("features", []))
    default_ds = datasets[0] if datasets else {}
    provider = default_ds.get("provider", "USGS_EPT")
    dataset_id = default_ds.get("dataset_id", default_ds.get("name", "dataset"))
    name_str = default_ds.get("name", dataset_id)
    raw_date = str(default_ds.get("date", "2022"))
    year = raw_date[:4] if len(raw_date) >= 4 else "2022"
    state = "CA"
    point_count = default_ds.get("point_count")
    point_density = default_ds.get("point_density")
    area_sqkm = default_ds.get("area_sqkm")
    
    # Collect all remote URLs
    urls: List[str] = []
    for d in datasets:
        u = d.get("url") or d.get("assets", {}).get("data", {}).get("href")
        if u:
            urls.append(u)
            
    # Generic additional metadata from provider
    additional_meta = default_ds.get("additional_metadata") or default_ds.get("raw_metadata") or {}

    # Export to Hive partitioned path catalog/grids/tilesize={tile_size}/buffer={buffer_size}/grid.gpkg
    hive_grid_dir.mkdir(parents=True, exist_ok=True)
    if gpkg_path.exists():
        gpkg_path.unlink()

    # Enrich grid dataframe with full metadata columns
    export_df = grid_gdf.copy()
    
    # Bounding boxes and WKT strings
    export_df["buffered_wkt"] = export_df["buffered_geometry"].apply(lambda g: g.wkt)
    export_df["core_bounds_str"] = export_df.geometry.apply(
        lambda g: f"([{g.bounds[0]}, {g.bounds[2]}], [{g.bounds[1]}, {g.bounds[3]}])"
    )
    export_df["buffered_bounds_str"] = export_df["buffered_geometry"].apply(
        lambda g: f"([{g.bounds[0]}, {g.bounds[2]}], [{g.bounds[1]}, {g.bounds[3]}])"
    )
    
    # Grid tile specifications
    export_df["tile_size"] = int(tile_size)
    export_df["buffer_size"] = int(buffer_size)
    export_df["grid_crs"] = str(crs_str)
    
    # File and Hive hierarchy names (pure Hive, without 'tiles/')
    hive_prefix = f"provider={provider}/dataset={dataset_id}/tilesize={tile_size}/buffer={buffer_size}"
    export_df["basename"] = export_df.apply(
        lambda r: f"{dataset_id}_tile_E{format_coord(r.geometry.bounds[0])}_N{format_coord(r.geometry.bounds[3])}",
        axis=1
    )
    export_df["hive_dir"] = hive_prefix
    export_df["hive_path"] = export_df["basename"].apply(lambda bn: f"{hive_prefix}/{bn}")
    export_df["spatial_basename"] = export_df["basename"]
    export_df["spatial_hive_path"] = export_df["hive_path"]
    
    # Dataset provenance
    export_df["provider"] = str(provider)
    export_df["dataset_id"] = str(dataset_id)
    export_df["name"] = str(name_str)
    export_df["date"] = str(raw_date)
    export_df["year"] = str(year)
    export_df["state"] = str(state)
    export_df["point_count"] = point_count if point_count is not None else None
    export_df["point_density"] = float(point_density) if point_density is not None else None
    export_df["area_sqkm"] = float(area_sqkm) if area_sqkm is not None else None
    
    # URLs and generic additional metadata
    export_df["source_urls"] = json.dumps(urls)
    export_df["additional_metadata_json"] = json.dumps(additional_meta, default=str)
    
    export_df.drop(columns=["buffered_geometry"], inplace=True)
    pyogrio.write_dataframe(export_df, gpkg_path, layer="grid", driver="GPKG")

    # Maintain primary fallback catalog/grid.gpkg
    primary_gpkg = ws / "catalog" / "grid.gpkg"
    pyogrio.write_dataframe(export_df, primary_gpkg, layer="grid", driver="GPKG")

    # Update manifest grids dictionary
    if "grids" not in manifest_data:
        manifest_data["grids"] = {}

    grid_key = f"tilesize={tile_size}_buffer={buffer_size}"
    manifest_data["grids"][grid_key] = {
        "tile_size": tile_size,
        "buffer_size": buffer_size,
        "grid_crs": crs_str,
        "total_tiles": len(export_df),
        "gpkg_file": f"grids/tilesize={tile_size}/buffer={buffer_size}/grid.gpkg"
    }
    manifest_data["grid_info"] = manifest_data["grids"][grid_key]

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    logger.info(f"Built workspace grid ({len(export_df)} tiles, size={tile_size}m, buf={buffer_size}m) at {gpkg_path}")
    return export_df, crs_str


def parse_quadrant_tile_id(tile_id: Union[int, str]) -> Tuple[int, List[str]]:
    """
    Parses a tile ID into a base integer index and optional quadrant tokens.
    Examples:
        15 -> (15, [])
        "15" -> (15, [])
        "15_NW" -> (15, ["NW"])
        "15_NW_SE" -> (15, ["NW", "SE"])
        "0015_NW" -> (15, ["NW"])
    """
    s = str(tile_id).strip()
    parts = s.split("_")
    try:
        base_id = int(parts[0])
    except ValueError:
        raise GridError(f"Invalid tile ID '{tile_id}': base identifier must be an integer.")

    quadrants = []
    for p in parts[1:]:
        up = p.upper()
        if up in ("NW", "NE", "SW", "SE"):
            quadrants.append(up)
        else:
            raise GridError(f"Invalid quadrant token '{p}' in tile ID '{tile_id}'. Must be one of NW, NE, SW, SE.")
    return base_id, quadrants


def get_tile_spec(
    manifest_or_grid_path: Union[str, Path],
    tile_id: Union[int, str],
    tile_size: int = 500,
    buffer_size: int = 50,
    overwrite: bool = False
) -> Dict[str, Any]:
    """
    Retrieves the spatial specification and complete multi-level metadata for a single tile ID.
    Supports integer base tile IDs (e.g. 15) and hierarchical quadrant string IDs (e.g. '15_NW').
    If the requested grid for (tile_size, buffer_size) does not exist on disk (or if overwrite=True),
    automatically builds the workspace grid first! (Single-command workflow).

    Args:
        manifest_or_grid_path (Union[str, Path]): Path to workspace root directory or manifest.json.
        tile_id (Union[int, str]): Target tile index or quadrant string (e.g. 15 or '15_NW').
        tile_size (int): Core metric tile size in meters (default: 1200m).
        buffer_size (int): Overlap buffer size in meters (default: 30m).
        overwrite (bool): If True, forces grid regeneration.

    Returns:
        Dict[str, Any]: Dictionary containing tile_id, core_poly, buffered_poly, grid_crs, urls,
                       dataset provenance, point metrics, and additional_metadata.
    """
    base_id, quadrants = parse_quadrant_tile_id(tile_id)

    path = Path(manifest_or_grid_path)
    if path.is_dir():
        ws_dir = path
    elif path.name == "manifest.json":
        ws_dir = path.parent.parent if path.parent.name == "catalog" else path.parent
    elif path.suffix.lower() == ".gpkg":
        ws_dir = path.parent.parent if path.parent.name == "catalog" or "tilesize=" in str(path) else path.parent
    else:
        ws_dir = path

    # Check for Hive partitioned grid: catalog/grids/tilesize={tile_size}/buffer={buffer_size}/grid.gpkg
    hive_gpkg = ws_dir / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}" / "grid.gpkg"
    primary_gpkg = ws_dir / "catalog" / "grid.gpkg" if (ws_dir / "catalog").exists() else ws_dir / "grid.gpkg"

    if hive_gpkg.exists() and not overwrite:
        gpkg_path = hive_gpkg
    elif primary_gpkg.exists() and not overwrite and (not (ws_dir / "catalog" / "catalog.gpkg").exists() or (tile_size == 1200 and buffer_size == 30)):
        gpkg_path = primary_gpkg
    else:
        # LAZY AUTO-BUILD or OVERWRITE
        logger.info(f"Building grid index (tile_size={tile_size}m, buffer={buffer_size}m, overwrite={overwrite})...")
        grid_gdf, crs_str = build_workspace_grid(ws_dir, tile_size=tile_size, buffer_size=buffer_size, overwrite=overwrite)
        gpkg_path = ws_dir / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}" / "grid.gpkg"
        if not gpkg_path.exists():
            gpkg_path = primary_gpkg

    # Memory-safe zero-copy single-row SQL query via pyogrio
    sql_query = f"SELECT * FROM grid WHERE tile_id = {base_id}"
    try:
        single_row_gdf = pyogrio.read_dataframe(gpkg_path, sql=sql_query)
    except Exception as e:
        raise GridError(f"Failed to query tile_id {base_id} from {gpkg_path}: {e}")

    if single_row_gdf.empty:
        raise GridError(f"Tile ID {base_id} not found in {gpkg_path}")

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
    buffered_bounds_str = row.get("buffered_bounds_str") or f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])"

    c_minx, c_miny, c_maxx, c_maxy = core_poly.bounds
    core_bounds_str = row.get("core_bounds_str") or f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])"

    # Handle hierarchical quadrant subdivision if quadrant tokens are present
    cur_core_poly = core_poly
    cur_tile_size = float(tile_size)
    cur_buffer_size = float(buffer_size)

    if quadrants:
        for q in quadrants:
            cur_minx, cur_miny, cur_maxx, cur_maxy = cur_core_poly.bounds
            x_mid = (cur_minx + cur_maxx) / 2.0
            y_mid = (cur_miny + cur_maxy) / 2.0
            if q == "NW":
                cur_core_poly = box(cur_minx, y_mid, x_mid, cur_maxy)
            elif q == "NE":
                cur_core_poly = box(x_mid, y_mid, cur_maxx, cur_maxy)
            elif q == "SW":
                cur_core_poly = box(cur_minx, cur_miny, x_mid, y_mid)
            elif q == "SE":
                cur_core_poly = box(x_mid, cur_miny, cur_maxx, y_mid)

            cur_tile_size = cur_tile_size / 2.0
            # Buffer remains fixed across subdivisions to preserve edge effect mitigation

        core_poly = cur_core_poly
        c_minx, c_miny, c_maxx, c_maxy = core_poly.bounds
        buffered_poly = box(
            c_minx - cur_buffer_size,
            c_miny - cur_buffer_size,
            c_maxx + cur_buffer_size,
            c_maxy + cur_buffer_size
        )
        b_minx, b_miny, b_maxx, b_maxy = buffered_poly.bounds
        buffered_bounds_str = f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])"
        core_bounds_str = f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])"

    # Parse URLs from source_urls column
    urls: List[str] = []
    if "source_urls" in row and isinstance(row["source_urls"], str):
        try:
            urls = json.loads(row["source_urls"])
        except Exception:
            urls = []

    # Parse additional / rando metadata
    additional_metadata: Dict[str, Any] = {}
    if "additional_metadata_json" in row and isinstance(row["additional_metadata_json"], str):
        try:
            additional_metadata = json.loads(row["additional_metadata_json"])
        except Exception:
            additional_metadata = {}

    dataset_id = str(row.get("dataset_id") or "")
    provider = str(row.get("provider") or "")
    name_str = str(row.get("name") or "")
    raw_date = str(row.get("date") or "2022")
    year = str(row.get("year") or raw_date[:4])
    state = str(row.get("state") or "CA")

    # Fallback to manifest.json if dataset provenance or URLs were missing from table
    if not urls or not dataset_id or dataset_id in ("unknown_dataset", "dataset"):
        manifest_path = ws_dir / "catalog" / "manifest.json" if (ws_dir / "catalog").exists() else ws_dir / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    m_data = json.load(mf)
                    datasets = m_data.get("datasets", m_data.get("features", []))
                    if datasets:
                        default_ds = datasets[0]
                        if not provider:
                            provider = str(default_ds.get("provider", "USGS_EPT"))
                        if not dataset_id or dataset_id in ("unknown_dataset", "dataset"):
                            dataset_id = str(default_ds.get("dataset_id", default_ds.get("name", "dataset")))
                        if not name_str:
                            name_str = str(default_ds.get("name", dataset_id))
                        if not urls:
                            for d in datasets:
                                u = d.get("url") or d.get("assets", {}).get("data", {}).get("href")
                                if u:
                                    urls.append(u)
                        if not additional_metadata:
                            additional_metadata = default_ds.get("additional_metadata") or default_ds.get("raw_metadata") or {}
            except Exception as e:
                logger.warning(f"Could not parse manifest fallback {manifest_path}: {e}")

    if not provider:
        provider = "USGS_EPT"
    if not dataset_id:
        dataset_id = "dataset"
    if not name_str:
        name_str = dataset_id

    quadrant_suffix = "_" + "_".join(quadrants) if quadrants else ""
    t_size = int(cur_tile_size)
    b_size = int(cur_buffer_size)

    # Master nominal grid sizes (to keep all tiles and subtiles in a single directory)
    nom_tile_size = int(row.get("tile_size") or tile_size or cur_tile_size)
    nom_buffer_size = int(row.get("buffer_size") or buffer_size or cur_buffer_size)

    # Upper-Left coordinates: West (minx), North (maxy) of the parent cell
    parent_geom = row.geometry
    ul_e_str = format_coord(parent_geom.bounds[0])
    ul_n_str = format_coord(parent_geom.bounds[3])

    tile_basename = f"{dataset_id}_tile_E{ul_e_str}_N{ul_n_str}{quadrant_suffix}"
    hive_dir = f"provider={provider}/dataset={dataset_id}/tilesize={nom_tile_size}/buffer={nom_buffer_size}"
    hive_path = f"{hive_dir}/{tile_basename}"

    # Unbuffered Core Bounds for direct cropping (PDAL, GDAL, Python, R)
    c_b = core_poly.bounds
    core_minx = round(float(c_b[0]), 2)
    core_miny = round(float(c_b[1]), 2)
    core_maxx = round(float(c_b[2]), 2)
    core_maxy = round(float(c_b[3]), 2)

    crop_bbox = [core_minx, core_miny, core_maxx, core_maxy]
    crop_pdal_bounds = f"([{core_minx}, {core_maxx}], [{core_miny}, {core_maxy}])"
    crop_gdal_te = f"{core_minx} {core_miny} {core_maxx} {core_maxy}"

    # Density & Hyper-Dense Memory Risk Calculation
    density = float(row.get("point_density") or 10.0)
    est_points = int(density * ((t_size + 2 * b_size) ** 2))
    floor_area = (25.0 + 2 * b_size) ** 2
    floor_points = int(density * floor_area)
    is_hyperdense = bool(floor_points >= 4_000_000)
    rec_mem = round((max(est_points, floor_points) * 250) / 1e9 * 1.5, 1)

    return {
        "tile_id": str(tile_id) if quadrants else int(base_id),
        "parent_tile_id": int(base_id),
        "quadrant": "_".join(quadrants) if quadrants else None,
        "level": len(quadrants),
        "tile_size": t_size,
        "buffer_size": b_size,
        "nominal_tile_size": nom_tile_size,
        "nominal_buffer_size": nom_buffer_size,
        "est_points": est_points,
        "is_hyperdense": is_hyperdense,
        "recommended_mem_gb": rec_mem,
        "basename": tile_basename,
        "hive_dir": hive_dir,
        "hive_path": hive_path,
        "spatial_basename": tile_basename,
        "spatial_hive_path": hive_path,
        "ul_easting": core_minx,
        "ul_northing": core_maxy,
        "crop_bbox": crop_bbox,
        "crop_pdal_bounds": crop_pdal_bounds,
        "crop_gdal_te": crop_gdal_te,
        "crop_minx": core_minx,
        "crop_miny": core_miny,
        "crop_maxx": core_maxx,
        "crop_maxy": core_maxy,
        "grid_gpkg_path": str(gpkg_path),
        "provider": provider,
        "year": year,
        "state": state,
        "date": raw_date,
        "name": name_str,
        "dataset_id": dataset_id,
        "point_count": row.get("point_count"),
        "point_density": row.get("point_density"),
        "area_sqkm": row.get("area_sqkm"),
        "core_poly": core_poly,
        "buffered_poly": buffered_poly,
        "grid_crs": grid_crs,
        "core_bounds_str": core_bounds_str,
        "buffered_bounds_str": buffered_bounds_str,
        "bbox_str": buffered_bounds_str,
        "urls": urls,
        "source_urls": urls,
        "additional_metadata": additional_metadata,
        "raw_metadata": additional_metadata,
    }



def get_grid_path(
    workspace_or_manifest: Union[str, Path],
    tile_size: int = 500,
    buffer_size: int = 50
) -> Path:
    """
    Returns the filesystem path to the Hive-partitioned grid.gpkg for given tile and buffer size.

    Args:
        workspace_or_manifest (Union[str, Path]): Workspace root or manifest.json path.
        tile_size (int): Core metric tile size in meters.
        buffer_size (int): Overlap buffer size in meters.

    Returns:
        Path: Path to the grid.gpkg file.
    """
    ws = Path(workspace_or_manifest)
    if ws.name == "manifest.json" or ws.suffix.lower() == ".gpkg":
        ws = ws.parent.parent if ws.parent.name == "catalog" else ws.parent

    hive_path = ws / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}" / "grid.gpkg"
    if hive_path.exists():
        return hive_path
    primary_path = ws / "catalog" / "grid.gpkg"
    if primary_path.exists():
        return primary_path
    return hive_path


def read_grid(
    workspace_or_manifest: Union[str, Path],
    tile_size: int = 500,
    buffer_size: int = 50,
    overwrite: bool = False
) -> gpd.GeoDataFrame:
    """
    Reads and returns the spatial grid as a GeoDataFrame for the requested tile and buffer configuration.
    Lazily generates the grid if not already present on disk or if overwrite=True.

    Args:
        workspace_or_manifest (Union[str, Path]): Workspace root or manifest.json path.
        tile_size (int): Core metric tile size in meters.
        buffer_size (int): Overlap buffer size in meters.
        overwrite (bool): If True, forces regeneration of the grid.

    Returns:
        gpd.GeoDataFrame: The grid vector layer.
    """
    grid_path = get_grid_path(workspace_or_manifest, tile_size=tile_size, buffer_size=buffer_size)
    if not grid_path.exists() or overwrite:
        build_workspace_grid(workspace_or_manifest, tile_size=tile_size, buffer_size=buffer_size, overwrite=overwrite)
        grid_path = get_grid_path(workspace_or_manifest, tile_size=tile_size, buffer_size=buffer_size)
    return gpd.read_file(grid_path)

