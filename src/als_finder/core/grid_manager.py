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
    tile_size: int = 1200,
    buffer_size: int = 30,
    target_crs: Optional[str] = None
) -> Tuple[gpd.GeoDataFrame, str]:
    """
    Automatically builds the spatial tile grid index for a workspace directory
    using the search catalog coverage layer (catalog.gpkg). Saves grid to Hive partitioned
    directory catalog/grids/tilesize={tile_size}/buffer={buffer_size}/grid.gpkg.

    Args:
        workspace_dir (Union[str, Path]): Path to workspace root directory.
        tile_size (int): Core metric tile size in meters (default: 1200m).
        buffer_size (int): Overlap buffer in meters (default: 30m).
        target_crs (Optional[str]): Explicit target metric CRS or None for auto-detection.

    Returns:
        Tuple[gpd.GeoDataFrame, str]: (grid_gdf, resolved_crs_string)
    """
    ws = Path(workspace_dir)
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
    
    # Export to Hive partitioned path catalog/grids/tilesize={tile_size}/buffer={buffer_size}/grid.gpkg
    hive_grid_dir = ws / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}"
    hive_grid_dir.mkdir(parents=True, exist_ok=True)
    gpkg_path = hive_grid_dir / "grid.gpkg"
    if gpkg_path.exists():
        gpkg_path.unlink()

    # Store buffered_geometry as WKT string
    export_df = grid_gdf.copy()
    export_df["buffered_wkt"] = export_df["buffered_geometry"].apply(lambda g: g.wkt)
    export_df.drop(columns=["buffered_geometry"], inplace=True)
    pyogrio.write_dataframe(export_df, gpkg_path, layer="grid", driver="GPKG")

    # Maintain primary fallback catalog/grid.gpkg
    primary_gpkg = ws / "catalog" / "grid.gpkg"
    pyogrio.write_dataframe(export_df, primary_gpkg, layer="grid", driver="GPKG")

    del export_df
    gc.collect()

    # Update manifest grids dictionary
    if "grids" not in manifest_data:
        manifest_data["grids"] = {}

    grid_key = f"tilesize={tile_size}_buffer={buffer_size}"
    manifest_data["grids"][grid_key] = {
        "tile_size": tile_size,
        "buffer_size": buffer_size,
        "grid_crs": crs_str,
        "total_tiles": len(grid_gdf),
        "gpkg_file": f"grids/tilesize={tile_size}/buffer={buffer_size}/grid.gpkg"
    }
    manifest_data["grid_info"] = manifest_data["grids"][grid_key]

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    logger.info(f"Built workspace grid ({len(grid_gdf)} tiles, size={tile_size}m, buf={buffer_size}m) at {gpkg_path}")
    return grid_gdf, crs_str


def get_tile_spec(
    manifest_or_grid_path: Union[str, Path],
    tile_id: int,
    tile_size: int = 1200,
    buffer_size: int = 30
) -> Dict[str, Any]:
    """
    Retrieves the spatial specification for a single tile ID.
    If the requested grid for (tile_size, buffer_size) does not exist on disk,
    automatically builds the workspace grid first! (Single-command workflow).

    Args:
        manifest_or_grid_path (Union[str, Path]): Path to workspace root directory or manifest.json.
        tile_id (int): Target zero-based tile ID.
        tile_size (int): Core metric tile size in meters (default: 1200m).
        buffer_size (int): Overlap buffer size in meters (default: 30m).

    Returns:
        Dict[str, Any]: Dictionary containing tile_id, core_poly, buffered_poly, grid_crs, and urls.
    """
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

    if hive_gpkg.exists():
        gpkg_path = hive_gpkg
    elif primary_gpkg.exists() and (not (ws_dir / "catalog" / "catalog.gpkg").exists() or (tile_size == 1200 and buffer_size == 30)):
        gpkg_path = primary_gpkg
    else:
        # LAZY AUTO-BUILD: Automatically build grid if not created yet!
        logger.info(f"Grid for tile_size={tile_size}m buffer={buffer_size}m not found. Auto-building grid index...")
        grid_gdf, crs_str = build_workspace_grid(ws_dir, tile_size=tile_size, buffer_size=buffer_size)
        gpkg_path = ws_dir / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}" / "grid.gpkg"
        if not gpkg_path.exists():
            gpkg_path = primary_gpkg

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
    buffered_bounds_str = f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])"

    c_minx, c_miny, c_maxx, c_maxy = core_poly.bounds
    core_bounds_str = f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])"

    # Read dataset metadata & urls from manifest if available
    urls: List[str] = []
    provider = "USGS_EPT"
    year = "2022"
    state = "CA"
    dataset_id = "unknown_dataset"

    manifest_path = ws_dir / "catalog" / "manifest.json" if (ws_dir / "catalog").exists() else ws_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as mf:
                m_data = json.load(mf)
                datasets = m_data.get("datasets", m_data.get("features", []))
                if datasets:
                    ds = datasets[0]
                    provider = ds.get("provider", provider)
                    dataset_id = ds.get("dataset_id", ds.get("name", dataset_id))
                    raw_date = str(ds.get("date", "2022"))
                    year = raw_date[:4] if len(raw_date) >= 4 else "2022"
                    for d in datasets:
                        url = d.get("url") or d.get("assets", {}).get("data", {}).get("href")
                        if url:
                            urls.append(url)
        except Exception as e:
            logger.warning(f"Could not parse metadata from manifest {manifest_path}: {e}")

    tile_basename = f"{dataset_id}_tile_{int(tile_id):04d}.laz"
    spatial_basename = f"{dataset_id}_tile_E{int(c_minx):07d}_N{int(c_miny):07d}_{tile_size}m.laz"

    # Aligns strictly with als-finder's standard upper-level Hive hierarchy: provider=*/dataset=*/
    hive_prefix = f"provider={provider}/dataset={dataset_id}"
    hive_path = f"{hive_prefix}/tiles/tilesize={tile_size}/buffer={buffer_size}/{tile_basename}"
    spatial_hive_path = f"{hive_prefix}/tiles/tilesize={tile_size}/buffer={buffer_size}/{spatial_basename}"

    return {
        "tile_id": int(tile_id),
        "basename": tile_basename,
        "spatial_basename": spatial_basename,
        "hive_path": hive_path,
        "spatial_hive_path": spatial_hive_path,
        "provider": provider,
        "year": year,
        "state": state,
        "dataset_id": dataset_id,
        "core_poly": core_poly,
        "buffered_poly": buffered_poly,
        "grid_crs": grid_crs,
        "core_bounds_str": core_bounds_str,
        "buffered_bounds_str": buffered_bounds_str,
        "bbox_str": buffered_bounds_str,
        "urls": urls,
    }
