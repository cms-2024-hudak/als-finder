"""
Grid and Tile Management Module for ALS-Finder.

Handles projected metric vector grid tile generation, tile index export (GeoPackage/JSON),
and zero-copy single-row spatial tile specification lookups.
"""

import gc
import json
import logging
import math
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import Polygon, MultiPolygon, box, shape
from shapely.wkt import loads as wkt_loads


logger = logging.getLogger(__name__)


class GridError(Exception):
    """Custom exception for grid processing errors."""
    pass


def invalidate_derived_catalog_artifacts(catalog_dir: Union[str, Path]) -> List[Path]:
    """
    Removes stale derived spatial grids and fetch arrays inside a workspace catalog directory
    whenever a fresh search or catalog update writes new manifest/catalog files.

    Args:
        catalog_dir (Union[str, Path]): Path to workspace `catalog/` directory.

    Returns:
        List[Path]: List of removed derived catalog paths.
    """
    removed: List[Path] = []
    cat_path = Path(catalog_dir)
    if not cat_path.exists():
        return removed
    primary_grid = cat_path / "grid.gpkg"
    if primary_grid.exists():
        try:
            primary_grid.unlink()
            removed.append(primary_grid)
        except Exception as e:
            logger.debug(f"Could not unlink stale {primary_grid}: {e}")
    grids_dir = cat_path / "grids"
    if grids_dir.exists() and grids_dir.is_dir():
        try:
            for gfile in grids_dir.rglob("*.gpkg"):
                removed.append(gfile)
            shutil.rmtree(grids_dir)
            removed.append(grids_dir)
        except Exception as e:
            logger.debug(f"Could not remove stale {grids_dir}: {e}")
    fetch_csv = cat_path / "fetch_array.csv"
    if fetch_csv.exists():
        try:
            fetch_csv.unlink()
            removed.append(fetch_csv)
        except Exception as e:
            logger.debug(f"Could not unlink stale {fetch_csv}: {e}")
    return removed


def _is_grid_stale(
    grid_gpkg_path: Path,
    ws_dir: Path,
    tile_size: Optional[int] = None,
    buffer_size: Optional[int] = None,
) -> bool:
    """
    Checks whether an existing grid.gpkg is stale relative to the workspace's manifest.json
    or catalog.gpkg (e.g. after a fresh search or update).
    """
    if not grid_gpkg_path.exists():
        return True
    cat_dir = ws_dir / "catalog" if (ws_dir / "catalog").exists() else ws_dir
    manifest_path = cat_dir / "manifest.json"
    catalog_gpkg = cat_dir / "catalog.gpkg"

    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m_data = json.load(f)
            exec_ts = m_data.get("execution_metadata", {}).get("timestamp_utc")
            grids = m_data.get("grids", {})
            if exec_ts:
                if not grids:
                    return True
                if tile_size is not None and buffer_size is not None:
                    g_key = f"tilesize={int(tile_size)}_buffer={int(buffer_size)}"
                    g_entry = grids.get(g_key) or grids.get("primary")
                    if g_entry and g_entry.get("catalog_timestamp_utc") and g_entry.get("catalog_timestamp_utc") != exec_ts:
                        return True
        except Exception:
            pass

    if catalog_gpkg.exists():
        try:
            if catalog_gpkg.stat().st_mtime > grid_gpkg_path.stat().st_mtime + 0.5:
                return True
        except Exception:
            pass
    return False


def _gpkg_has_grid_layer(gpkg_path: Path) -> bool:
    """Return True if the specified GeoPackage exists and contains a layer named 'grid'."""
    if not gpkg_path.exists() or not gpkg_path.is_file() or gpkg_path.suffix.lower() != ".gpkg":
        return False
    try:
        layers = pyogrio.list_layers(gpkg_path)
        return any(str(row[0]) == "grid" for row in layers)
    except Exception:
        return False


def _estimate_utm_epsg_from_lonlat(lon: float, lat: float) -> str:
    """Deterministically compute WGS84 UTM EPSG code from (lon, lat) in degrees."""
    zone = int(math.floor((float(lon) + 180.0) / 6.0) + 1)
    zone = max(1, min(60, zone))
    epsg = (32600 + zone) if float(lat) >= 0.0 else (32700 + zone)
    return f"EPSG:{epsg}"


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


def _grid_single_crs_gdf(
    gdf: gpd.GeoDataFrame,
    tile_size: int,
    buffer_size: int,
    grid_crs: str,
) -> gpd.GeoDataFrame:
    """ Build a snapped metric vector grid for a single projected CRS."""
    projected_gdf = gdf.to_crs(grid_crs) if gdf.crs else gdf.set_crs(grid_crs)

    minx, miny, maxx, maxy = projected_gdf.total_bounds
    if math.isnan(minx) or math.isnan(miny) or math.isnan(maxx) or math.isnan(maxy):
        raise GridError("GeoDataFrame total bounds contain NaN values.")

    minx = math.floor(minx / tile_size) * tile_size
    miny = math.floor(miny / tile_size) * tile_size
    maxx = math.ceil(maxx / tile_size) * tile_size
    maxy = math.ceil(maxy / tile_size) * tile_size

    import numpy as np
    import shapely

    xs = np.arange(minx, maxx, tile_size)
    ys = np.arange(miny, maxy, tile_size)
    xx, yy = np.meshgrid(xs, ys, indexing="ij")
    xx_f = xx.ravel()
    yy_f = yy.ravel()

    buffered_boxes = shapely.box(
        xx_f - buffer_size,
        yy_f - buffer_size,
        xx_f + tile_size + buffer_size,
        yy_f + tile_size + buffer_size,
    )

    sindex = projected_gdf.sindex
    geom_indices, _ = sindex.query(buffered_boxes, predicate="intersects")
    valid_indices = np.unique(geom_indices)

    if len(valid_indices) == 0:
        raise GridError("No grid tiles intersected the input ROI geometry.")

    valid_indices.sort()

    sel_xx = xx_f[valid_indices]
    sel_yy = yy_f[valid_indices]

    core_geoms = shapely.box(sel_xx, sel_yy, sel_xx + tile_size, sel_yy + tile_size)
    buffered_geoms = buffered_boxes[valid_indices]

    out_gdf = gpd.GeoDataFrame(
        {
            "tile_id": list(range(len(valid_indices))),
            "grid_crs": [grid_crs] * len(valid_indices),
            "core_wkt": [g.wkt for g in core_geoms],
            "buffered_wkt": [g.wkt for g in buffered_geoms],
            "buffered_geometry": buffered_geoms,
        },
        geometry=core_geoms,
        crs=grid_crs,
    )
    return out_gdf


def _is_1to1_sample_plot_gdf(
    gdf: gpd.GeoDataFrame,
    tile_size: int,
    target_crs: Optional[str] = None,
) -> bool:
    """
    Detect whether the input GeoDataFrame represents discrete 1:1 sample plots
    whose geometries already match `tile_size x tile_size` in their local UTM CRS
    (or carry explicit sample/tile metadata columns).
    """
    cols = set(gdf.columns)
    if any(c in cols for c in ("sample_id", "core_wkt", "core_minx", "buffered_wkt")):
        if "core_minx" in cols and "core_maxx" in cols:
            try:
                widths = (gdf["core_maxx"].astype(float) - gdf["core_minx"].astype(float)).abs()
                if (widths - float(tile_size)).abs().max() <= 2.0:
                    return True
            except Exception:
                pass
        else:
            return True

    if "tile_id" in cols and "grid_crs" in cols:
        return True

    # For single-row inputs with an explicit target_crs (and no sample columns), keep standard snapping
    if len(gdf) == 1 and target_crs is not None:
        return False

    try:
        wgs_gdf = gdf.to_crs("EPSG:4326") if (gdf.crs and gdf.crs.to_string() != "EPSG:4326") else gdf.copy()
        if wgs_gdf.crs is None:
            wgs_gdf.set_crs("EPSG:4326", inplace=True)

        for idx, row in wgs_gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty or isinstance(geom, MultiPolygon):
                return False
            c = geom.centroid
            row_crs = (
                str(row["grid_crs"]).strip()
                if ("grid_crs" in cols and pd.notna(row.get("grid_crs")) and str(row.get("grid_crs")).strip())
                else (target_crs if (target_crs and target_crs.lower() != "auto") else _estimate_utm_epsg_from_lonlat(c.x, c.y))
            )
            utm_geom = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(row_crs).iloc[0]
            b0, b1, b2, b3 = utm_geom.bounds
            if abs((b2 - b0) - float(tile_size)) > 2.5 or abs((b3 - b1) - float(tile_size)) > 2.5:
                return False
        return True
    except Exception:
        return False


def create_tile_grid_index(
    gdf: gpd.GeoDataFrame,
    tile_size: int = 500,
    buffer_size: int = 50,
    target_crs: Optional[str] = None
) -> Tuple[gpd.GeoDataFrame, str]:
    """
    Generates a vector grid over the input GeoDataFrame.
    - For standard single-region ROIs, snaps bounds to the nearest tile_size step in projected metric space.
    - For 1:1 pre-sized sample plot GeoPackages (spanning one or multiple UTM zones), preserves a strict
      1:1 feature-to-tile mapping (`tile_id = 0..N-1`) with each tile's dynamic local UTM `grid_crs`,
      `core_wkt`, and `buffered_wkt` without allocating a continental bounding-box mesh.
    - For multi-polygon ROIs spanning multiple UTM zones (>6 degrees longitude), grids each disjoint
      polygon in its local UTM zone.

    Args:
        gdf (gpd.GeoDataFrame): Input ROI spatial layer.
        tile_size (int): Core tile size in meters (default: 500m).
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

    # Mode 1: 1:1 Sample Plot / Pre-Tiled GeoDataFrame
    if _is_1to1_sample_plot_gdf(gdf, tile_size=tile_size, target_crs=target_crs):
        wgs_gdf = gdf.to_crs("EPSG:4326") if (gdf.crs and gdf.crs.to_string() != "EPSG:4326") else gdf.copy()
        if wgs_gdf.crs is None:
            wgs_gdf.set_crs("EPSG:4326", inplace=True)

        cols = set(wgs_gdf.columns)
        records: List[Dict[str, Any]] = []
        core_polys_utm: List[Polygon] = []
        buf_polys_utm: List[Polygon] = []
        core_polys_wgs84: List[Polygon] = []
        crs_list: List[str] = []

        for idx, (_, row) in enumerate(wgs_gdf.iterrows()):
            geom_wgs = row.geometry
            c = geom_wgs.centroid
            if target_crs and target_crs.lower() != "auto":
                row_crs = target_crs
            elif "grid_crs" in cols and pd.notna(row.get("grid_crs")) and str(row.get("grid_crs")).strip():
                row_crs = str(row.get("grid_crs")).strip()
            else:
                row_crs = _estimate_utm_epsg_from_lonlat(c.x, c.y)

            if "core_wkt" in cols and isinstance(row.get("core_wkt"), str) and row["core_wkt"].strip():
                core_utm = wkt_loads(row["core_wkt"])
            elif (
                "core_minx" in cols
                and pd.notna(row.get("core_minx"))
                and pd.notna(row.get("core_maxx"))
                and abs((float(row["core_maxx"]) - float(row["core_minx"])) - float(tile_size)) <= 2.0
            ):
                c_minx = round(float(row["core_minx"]), 2)
                c_miny = round(float(row["core_miny"]), 2)
                c_maxx = round(float(row["core_maxx"]), 2)
                c_maxy = round(float(row["core_maxy"]), 2)
                core_utm = box(c_minx, c_miny, c_maxx, c_maxy)
            else:
                utm_g = gpd.GeoSeries([geom_wgs], crs="EPSG:4326").to_crs(row_crs).iloc[0]
                b0, b1, _, _ = utm_g.bounds
                c_minx = round(float(b0), 1)
                c_miny = round(float(b1), 1)
                core_utm = box(c_minx, c_miny, c_minx + float(tile_size), c_miny + float(tile_size))

            c_minx, c_miny, c_maxx, c_maxy = core_utm.bounds
            buf_utm = box(
                c_minx - float(buffer_size),
                c_miny - float(buffer_size),
                c_maxx + float(buffer_size),
                c_maxy + float(buffer_size),
            )
            core_wgs = gpd.GeoSeries([core_utm], crs=row_crs).to_crs("EPSG:4326").iloc[0]

            rec = {k: row[k] for k in wgs_gdf.columns if k != "geometry"}
            rec["tile_id"] = idx
            rec["grid_crs"] = row_crs
            rec["core_wkt"] = core_utm.wkt
            rec["buffered_wkt"] = buf_utm.wkt
            rec["core_minx"] = round(float(c_minx), 2)
            rec["core_miny"] = round(float(c_miny), 2)
            rec["core_maxx"] = round(float(c_maxx), 2)
            rec["core_maxy"] = round(float(c_maxy), 2)
            rec["buffered_minx"] = round(float(c_minx - buffer_size), 2)
            rec["buffered_miny"] = round(float(c_miny - buffer_size), 2)
            rec["buffered_maxx"] = round(float(c_maxx + buffer_size), 2)
            rec["buffered_maxy"] = round(float(c_maxy + buffer_size), 2)
            rec["buffered_geometry"] = buf_utm
            records.append(rec)
            core_polys_utm.append(core_utm)
            buf_polys_utm.append(buf_utm)
            core_polys_wgs84.append(core_wgs)
            crs_list.append(row_crs)

        unique_crs = sorted(set(crs_list))
        if len(unique_crs) == 1:
            resolved_crs = unique_crs[0]
            grid_gdf = gpd.GeoDataFrame(records, geometry=core_polys_utm, crs=resolved_crs)
        else:
            resolved_crs = "EPSG:4326"
            grid_gdf = gpd.GeoDataFrame(records, geometry=core_polys_wgs84, crs="EPSG:4326")

        logger.info(
            f"Preserved {len(grid_gdf)} 1:1 sample plot tiles across {len(unique_crs)} UTM zone(s) "
            f"(tile={tile_size}m, buffer={buffer_size}m)"
        )
        return grid_gdf, resolved_crs

    # Mode 2: Check for multi-zone disjoint polygons (>6 degrees longitude span with auto CRS)
    if not target_crs or target_crs.lower() == "auto":
        try:
            wgs_gdf = gdf.to_crs("EPSG:4326") if (gdf.crs and gdf.crs.to_string() != "EPSG:4326") else gdf.copy()
            if wgs_gdf.crs is None:
                wgs_gdf.set_crs("EPSG:4326", inplace=True)
            exploded = wgs_gdf.explode(index_parts=False).reset_index(drop=True)
            minx_wgs, _, maxx_wgs, _ = exploded.total_bounds
            if len(exploded) > 1 and abs(maxx_wgs - minx_wgs) > 6.0:
                part_frames: List[gpd.GeoDataFrame] = []
                crs_seen: List[str] = []
                running_id = 0
                for _, part_row in exploded.iterrows():
                    part_geom = part_row.geometry
                    if part_geom is None or part_geom.is_empty:
                        continue
                    c = part_geom.centroid
                    part_crs = _estimate_utm_epsg_from_lonlat(c.x, c.y)
                    part_single = gpd.GeoDataFrame([part_row], geometry=[part_geom], crs="EPSG:4326")
                    part_grid = _grid_single_crs_gdf(part_single, tile_size=tile_size, buffer_size=buffer_size, grid_crs=part_crs)
                    part_grid["tile_id"] = list(range(running_id, running_id + len(part_grid)))
                    running_id += len(part_grid)
                    crs_seen.append(part_crs)
                    part_grid_wgs = part_grid.to_crs("EPSG:4326")
                    part_frames.append(part_grid_wgs)

                if part_frames:
                    combined = gpd.GeoDataFrame(pd.concat(part_frames, ignore_index=True), crs="EPSG:4326")
                    unique_crs = sorted(set(crs_seen))
                    if len(unique_crs) == 1:
                        only_crs = unique_crs[0]
                        combined["geometry"] = [wkt_loads(w) for w in combined["core_wkt"]]
                        combined = combined.set_crs(only_crs, allow_override=True)
                        return combined, only_crs
                    return combined, "EPSG:4326"
        except Exception as e:
            logger.debug(f"Multi-zone disjoint gridding fallback: {e}")

    # Mode 3: Standard single projected CRS grid
    grid_crs = resolve_projected_crs(gdf, target_crs=target_crs)
    grid_gdf = _grid_single_crs_gdf(gdf, tile_size=tile_size, buffer_size=buffer_size, grid_crs=grid_crs)
    logger.info(f"Generated {len(grid_gdf)} metric tiles in {grid_crs} (tile={tile_size}m, buffer={buffer_size}m)")
    return grid_gdf, grid_crs


def _enrich_grid_with_datasets(
    grid_gdf: gpd.GeoDataFrame,
    manifest_data: Optional[Dict[str, Any]],
    tile_size: int,
    buffer_size: int,
    default_crs_str: str,
) -> gpd.GeoDataFrame:
    """
    Enriches a grid GeoDataFrame with per-tile metric bounds (`core_wkt`, `buffered_wkt`),
    Hive path columns, and spatially matched dataset provenance (`provider`, `dataset_id`,
    `source_urls`, `date`, `year`, `state`, `point_density`).
    """
    export_df = grid_gdf.copy()
    t_size = int(tile_size) if tile_size is not None else 1200
    b_size = int(buffer_size) if buffer_size is not None else 30

    datasets: List[Dict[str, Any]] = []
    if manifest_data and isinstance(manifest_data, dict):
        datasets = manifest_data.get("datasets", manifest_data.get("features", [])) or []

    default_ds = datasets[0] if datasets else {}
    def_provider = str(default_ds.get("provider", "USGS_EPT"))
    def_dataset_id = str(default_ds.get("dataset_id") or default_ds.get("name") or "dataset")
    def_name = str(default_ds.get("name") or def_dataset_id)
    def_raw_date = str(default_ds.get("date") or "2022")
    def_year = def_raw_date[:4] if len(def_raw_date) >= 4 else "2022"
    def_state = str(default_ds.get("state") or "CA")
    def_point_count = default_ds.get("point_count")
    def_point_density = default_ds.get("point_density")
    def_area_sqkm = default_ds.get("area_sqkm")
    def_add_meta = default_ds.get("additional_metadata") or default_ds.get("raw_metadata") or {}

    all_urls: List[str] = []
    ds_by_id: Dict[str, Dict[str, Any]] = {}
    spatial_datasets: List[Tuple[Any, Dict[str, Any]]] = []

    for d in datasets:
        u = d.get("url") or d.get("assets", {}).get("data", {}).get("href")
        if u:
            all_urls.append(u)
        d_id = str(d.get("dataset_id") or d.get("name") or "")
        if d_id:
            ds_by_id[d_id] = d
        d_geom = None
        try:
            raw_g = d.get("geometry")
            if raw_g and isinstance(raw_g, dict) and "coordinates" in raw_g:
                d_geom = shape(raw_g)
            elif d.get("bounds") and len(d.get("bounds")) >= 4:
                b = d["bounds"]
                d_geom = box(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        except Exception:
            d_geom = None
        if d_geom is not None and not d_geom.is_empty:
            spatial_datasets.append((d_geom, d))

    # Prepare WGS84 geometries if we need spatial matching across multiple datasets
    wgs_geoms: Optional[List[Any]] = None
    if len(spatial_datasets) > 1:
        try:
            wgs_series = export_df.geometry
            if export_df.crs and export_df.crs.to_string() != "EPSG:4326":
                wgs_series = export_df.to_crs("EPSG:4326").geometry
            wgs_geoms = list(wgs_series)
        except Exception:
            wgs_geoms = None

    cols = set(export_df.columns)
    core_wkts: List[str] = []
    buf_wkts: List[str] = []
    core_bounds_strs: List[str] = []
    buf_bounds_strs: List[str] = []
    grid_crs_col: List[str] = []
    basenames: List[str] = []
    hive_dirs: List[str] = []
    hive_paths: List[str] = []
    providers: List[str] = []
    dataset_ids: List[str] = []
    names: List[str] = []
    dates: List[str] = []
    years: List[str] = []
    states: List[str] = []
    point_counts: List[Any] = []
    point_densities: List[Optional[float]] = []
    area_sqkms: List[Optional[float]] = []
    source_urls_col: List[str] = []
    add_meta_col: List[str] = []

    for row_idx, (_, row) in enumerate(export_df.iterrows()):
        row_crs = (
            str(row["grid_crs"]).strip()
            if ("grid_crs" in cols and pd.notna(row.get("grid_crs")) and str(row.get("grid_crs")).strip())
            else str(default_crs_str)
        )
        grid_crs_col.append(row_crs)

        if "core_wkt" in cols and isinstance(row.get("core_wkt"), str) and row["core_wkt"].strip():
            c_poly = wkt_loads(row["core_wkt"])
        else:
            c_poly = row.geometry

        if "buffered_wkt" in cols and isinstance(row.get("buffered_wkt"), str) and row["buffered_wkt"].strip():
            b_poly = wkt_loads(row["buffered_wkt"])
        elif "buffered_geometry" in cols and row.get("buffered_geometry") is not None:
            b_poly = row["buffered_geometry"]
        else:
            cb0, cb1, cb2, cb3 = c_poly.bounds
            b_poly = box(cb0 - b_size, cb1 - b_size, cb2 + b_size, cb3 + b_size)

        core_wkts.append(c_poly.wkt)
        buf_wkts.append(b_poly.wkt)
        c_minx, c_miny, c_maxx, c_maxy = c_poly.bounds
        b_minx, b_miny, b_maxx, b_maxy = b_poly.bounds
        core_bounds_strs.append(f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])")
        buf_bounds_strs.append(f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])")

        # Resolve per-row dataset provenance
        row_ds_id = str(row.get("dataset_id") or "").strip() if "dataset_id" in cols and pd.notna(row.get("dataset_id")) else ""
        row_prov = str(row.get("provider") or "").strip() if "provider" in cols and pd.notna(row.get("provider")) else ""

        matched_ds: Optional[Dict[str, Any]] = None
        if row_ds_id and row_ds_id not in ("dataset", "unknown_dataset") and row_ds_id in ds_by_id:
            matched_ds = ds_by_id[row_ds_id]
        elif (not row_ds_id or row_ds_id in ("dataset", "unknown_dataset")) and wgs_geoms is not None:
            tile_wgs = wgs_geoms[row_idx]
            for d_geom, d_dict in spatial_datasets:
                try:
                    if d_geom.intersects(tile_wgs):
                        matched_ds = d_dict
                        break
                except Exception:
                    continue

        if row_ds_id and row_ds_id not in ("dataset", "unknown_dataset"):
            ds_id = row_ds_id
            prov = row_prov or (str(matched_ds.get("provider")) if matched_ds else def_provider)
            nm = (
                str(row.get("name"))
                if ("name" in cols and pd.notna(row.get("name")) and str(row.get("name")).strip())
                else (str(matched_ds.get("name") or ds_id) if matched_ds else ds_id)
            )
            dt = (
                str(row.get("date") or row.get("collect_end") or row.get("collect_start") or "")
                if any(k in cols and pd.notna(row.get(k)) for k in ("date", "collect_end", "collect_start"))
                else (str(matched_ds.get("date") or def_raw_date) if matched_ds else def_raw_date)
            )
            yr = (
                str(row.get("year") or row.get("collect_year") or dt[:4] or "2022")
                if any(k in cols and pd.notna(row.get(k)) for k in ("year", "collect_year"))
                else (dt[:4] if len(dt) >= 4 else "2022")
            )
            st = (
                str(row.get("state") or row.get("state_abbr") or "US")
                if any(k in cols and pd.notna(row.get(k)) for k in ("state", "state_abbr"))
                else (str(matched_ds.get("state") or def_state) if matched_ds else def_state)
            )
            p_cnt = row.get("point_count") if "point_count" in cols and pd.notna(row.get("point_count")) else (matched_ds.get("point_count") if matched_ds else def_point_count)
            p_dens = row.get("point_density") if "point_density" in cols and pd.notna(row.get("point_density")) else (matched_ds.get("point_density") if matched_ds else def_point_density)
            a_sqkm = row.get("area_sqkm") if "area_sqkm" in cols and pd.notna(row.get("area_sqkm")) else (matched_ds.get("area_sqkm") if matched_ds else def_area_sqkm)

            row_urls: List[str] = []
            if "source_urls" in cols and isinstance(row.get("source_urls"), str) and row["source_urls"].strip():
                try:
                    parsed_u = json.loads(row["source_urls"])
                    if isinstance(parsed_u, list):
                        row_urls = [str(x) for x in parsed_u if x]
                except Exception:
                    row_urls = [str(row["source_urls"])]
            elif "source_url" in cols and pd.notna(row.get("source_url")) and str(row.get("source_url")).strip():
                row_urls = [str(row["source_url"]).strip()]
            elif matched_ds:
                u = matched_ds.get("url") or matched_ds.get("assets", {}).get("data", {}).get("href")
                if u:
                    row_urls = [str(u)]
            if not row_urls:
                row_urls = all_urls

            if "additional_metadata_json" in cols and isinstance(row.get("additional_metadata_json"), str) and row["additional_metadata_json"].strip():
                row_meta_json = row["additional_metadata_json"]
            elif matched_ds:
                row_meta_json = json.dumps(matched_ds.get("additional_metadata") or matched_ds.get("raw_metadata") or {}, default=str)
            else:
                row_meta_json = json.dumps(def_add_meta, default=str)
        elif matched_ds is not None:
            prov = str(matched_ds.get("provider") or def_provider)
            ds_id = str(matched_ds.get("dataset_id") or matched_ds.get("name") or def_dataset_id)
            nm = str(matched_ds.get("name") or ds_id)
            dt = str(matched_ds.get("date") or def_raw_date)
            yr = dt[:4] if len(dt) >= 4 else "2022"
            st = str(matched_ds.get("state") or row.get("state_abbr") or row.get("state") or def_state)
            p_cnt = matched_ds.get("point_count")
            p_dens = matched_ds.get("point_density")
            a_sqkm = matched_ds.get("area_sqkm")
            u = matched_ds.get("url") or matched_ds.get("assets", {}).get("data", {}).get("href")
            row_urls = [str(u)] if u else all_urls
            row_meta_json = json.dumps(matched_ds.get("additional_metadata") or matched_ds.get("raw_metadata") or {}, default=str)
        else:
            prov = def_provider
            ds_id = def_dataset_id
            nm = def_name
            dt = def_raw_date
            yr = def_year
            st = str(row.get("state_abbr") or row.get("state") or def_state)
            p_cnt = def_point_count
            p_dens = def_point_density
            a_sqkm = def_area_sqkm
            row_urls = all_urls
            row_meta_json = json.dumps(def_add_meta, default=str)

        ul_e = format_coord(c_minx)
        ul_n = format_coord(c_maxy)
        b_name = f"{ds_id}_tile_E{ul_e}_N{ul_n}"
        h_dir = f"provider={prov}/dataset={ds_id}/tilesize={t_size}/buffer={b_size}"
        h_path = f"{h_dir}/{b_name}"

        basenames.append(b_name)
        hive_dirs.append(h_dir)
        hive_paths.append(h_path)
        providers.append(prov)
        dataset_ids.append(ds_id)
        names.append(nm)
        dates.append(dt)
        years.append(yr)
        states.append(st)
        point_counts.append(p_cnt if p_cnt is not None else None)
        point_densities.append(float(p_dens) if p_dens is not None and not (isinstance(p_dens, float) and math.isnan(p_dens)) else None)
        area_sqkms.append(float(a_sqkm) if a_sqkm is not None and not (isinstance(a_sqkm, float) and math.isnan(a_sqkm)) else None)
        source_urls_col.append(json.dumps(row_urls))
        add_meta_col.append(row_meta_json)

    export_df["core_wkt"] = core_wkts
    export_df["buffered_wkt"] = buf_wkts
    export_df["core_bounds_str"] = core_bounds_strs
    export_df["buffered_bounds_str"] = buf_bounds_strs
    export_df["tile_size"] = t_size
    export_df["buffer_size"] = b_size
    export_df["grid_crs"] = grid_crs_col
    export_df["basename"] = basenames
    export_df["hive_dir"] = hive_dirs
    export_df["hive_path"] = hive_paths
    export_df["spatial_basename"] = basenames
    export_df["spatial_hive_path"] = hive_paths
    export_df["provider"] = providers
    export_df["dataset_id"] = dataset_ids
    export_df["name"] = names
    export_df["date"] = dates
    export_df["year"] = years
    export_df["state"] = states
    export_df["point_count"] = point_counts
    export_df["point_density"] = point_densities
    export_df["area_sqkm"] = area_sqkms
    export_df["source_urls"] = source_urls_col
    export_df["additional_metadata_json"] = add_meta_col

    if "buffered_geometry" in export_df.columns:
        export_df = export_df.drop(columns=["buffered_geometry"])

    return export_df


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

    if tile_size is None and hasattr(grid_gdf, "attrs") and "tile_size" in grid_gdf.attrs:
        tile_size = grid_gdf.attrs["tile_size"]
    if buffer_size is None and hasattr(grid_gdf, "attrs") and "buffer_size" in grid_gdf.attrs:
        buffer_size = grid_gdf.attrs["buffer_size"]

    output_dir.mkdir(parents=True, exist_ok=True)
    gpkg_path = output_dir / "grid.gpkg"
    manifest_path = output_dir / "manifest.json"

    if gpkg_path.exists():
        gpkg_path.unlink()

    t_size = int(tile_size) if tile_size is not None else 1200
    b_size = int(buffer_size) if buffer_size is not None else 30
    default_crs = grid_gdf.crs.to_string() if grid_gdf.crs else "EPSG:3857"

    export_df = _enrich_grid_with_datasets(
        grid_gdf,
        manifest_data=manifest_data,
        tile_size=t_size,
        buffer_size=b_size,
        default_crs_str=default_crs,
    )

    num_rows = len(export_df)
    for start_idx in range(0, num_rows, batch_size):
        chunk = export_df.iloc[start_idx : start_idx + batch_size]
        is_append = gpkg_path.exists()
        pyogrio.write_dataframe(chunk, gpkg_path, layer="grid", driver="GPKG", append=is_append)
        del chunk
        gc.collect()

    del export_df
    gc.collect()

    updated_manifest = dict(manifest_data) if manifest_data else {}
    if "grids" not in updated_manifest:
        updated_manifest["grids"] = {}

    rel_gpkg_str = str(gpkg_path.relative_to(output_dir)) if gpkg_path.is_relative_to(output_dir) else gpkg_path.name
    grid_key = f"tilesize={tile_size}_buffer={buffer_size}" if tile_size is not None and buffer_size is not None else "primary"
    exec_ts = updated_manifest.get("execution_metadata", {}).get("timestamp_utc")

    updated_manifest["grids"][grid_key] = {
        "tile_size": tile_size,
        "buffer_size": buffer_size,
        "grid_crs": default_crs,
        "total_tiles": len(grid_gdf),
        "gpkg_file": rel_gpkg_str,
        "catalog_timestamp_utc": exec_ts,
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
        workspace_dir (Union[str, Path]): Path to workspace root directory, manifest.json, or standalone .gpkg.
        tile_size (int): Core metric tile size in meters (default: 500m).
        buffer_size (int): Overlap buffer in meters (default: 50m).
        target_crs (Optional[str]): Explicit target metric CRS or None for auto-detection.
        overwrite (bool): If True, forces regeneration of the grid even if grid.gpkg exists.

    Returns:
        Tuple[gpd.GeoDataFrame, str]: (grid_gdf, resolved_crs_string)
    """
    raw_input = Path(workspace_dir)
    if raw_input.name == "manifest.json" or raw_input.suffix.lower() == ".gpkg":
        ws = raw_input.parent.parent if raw_input.parent.name == "catalog" else raw_input.parent
    else:
        ws = raw_input

    hive_grid_dir = ws / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}"
    gpkg_path = hive_grid_dir / "grid.gpkg"

    if gpkg_path.exists() and not overwrite and not _is_grid_stale(gpkg_path, ws, tile_size=tile_size, buffer_size=buffer_size):
        logger.info(f"Using existing grid at {gpkg_path} (use overwrite=True to rebuild)")
        existing_gdf = pyogrio.read_dataframe(gpkg_path, layer="grid") if _gpkg_has_grid_layer(gpkg_path) else pyogrio.read_dataframe(gpkg_path)
        crs_str = existing_gdf.crs.to_string() if existing_gdf.crs else "EPSG:3857"
        return existing_gdf, crs_str

    catalog_gpkg = ws / "catalog" / "catalog.gpkg"
    manifest_path = ws / "catalog" / "manifest.json"

    manifest_data: Dict[str, Any] = {}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

    # Prioritize workspace-cached ROI or manifest ROI geometry over raw remote acquisition footprints
    roi_file: Optional[Path] = None
    for candidate in [ws / "catalog" / "roi.gpkg", ws / "roi.gpkg"]:
        if candidate.exists():
            roi_file = candidate
            break
    if roi_file is None and "search_parameters" in manifest_data and manifest_data["search_parameters"].get("roi"):
        candidate_roi = Path(manifest_data["search_parameters"]["roi"])
        if candidate_roi.exists():
            roi_file = candidate_roi
        elif (ws / candidate_roi).exists():
            roi_file = ws / candidate_roi

    if roi_file is not None:
        logger.info(f"Building spatial grid from workspace ROI: {roi_file}")
        source_gdf = gpd.read_file(roi_file)
    elif raw_input.is_file() and raw_input.suffix.lower() == ".gpkg" and raw_input.name != "catalog.gpkg":
        logger.info(f"Building spatial grid from direct GeoPackage input: {raw_input}")
        source_gdf = gpd.read_file(raw_input, layer="grid") if _gpkg_has_grid_layer(raw_input) else gpd.read_file(raw_input)
    elif catalog_gpkg.exists():
        logger.info("No dedicated ROI file found; building spatial grid from catalog footprint.")
        source_gdf = gpd.read_file(catalog_gpkg)
    else:
        raise GridError(f"Catalog GeoPackage not found at {catalog_gpkg}. Please run search first.")

    grid_gdf, crs_str = create_tile_grid_index(
        source_gdf,
        tile_size=tile_size,
        buffer_size=buffer_size,
        target_crs=target_crs
    )

    hive_grid_dir.mkdir(parents=True, exist_ok=True)
    if gpkg_path.exists():
        gpkg_path.unlink()

    export_df = _enrich_grid_with_datasets(
        grid_gdf,
        manifest_data=manifest_data,
        tile_size=int(tile_size),
        buffer_size=int(buffer_size),
        default_crs_str=crs_str,
    )

    pyogrio.write_dataframe(export_df, gpkg_path, layer="grid", driver="GPKG")

    primary_gpkg = ws / "catalog" / "grid.gpkg"
    primary_gpkg.parent.mkdir(parents=True, exist_ok=True)
    if primary_gpkg.exists():
        primary_gpkg.unlink()
    pyogrio.write_dataframe(export_df, primary_gpkg, layer="grid", driver="GPKG")

    if manifest_path.exists() or manifest_data:
        if "grids" not in manifest_data:
            manifest_data["grids"] = {}

        grid_key = f"tilesize={tile_size}_buffer={buffer_size}"
        exec_ts = manifest_data.get("execution_metadata", {}).get("timestamp_utc")
        manifest_data["grids"][grid_key] = {
            "tile_size": tile_size,
            "buffer_size": buffer_size,
            "grid_crs": crs_str,
            "total_tiles": len(export_df),
            "gpkg_file": f"grids/tilesize={tile_size}/buffer={buffer_size}/grid.gpkg",
            "catalog_timestamp_utc": exec_ts,
        }
        manifest_data["grid_info"] = manifest_data["grids"][grid_key]

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
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
    Supports integer base tile IDs (e.g. 15), hierarchical quadrant string IDs (e.g. '15_NW'),
    and direct standalone GeoPackages containing a `grid` layer (including multi-UTM sample catalogs).
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

    hive_gpkg = ws_dir / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}" / "grid.gpkg"
    primary_gpkg = ws_dir / "catalog" / "grid.gpkg" if (ws_dir / "catalog").exists() else ws_dir / "grid.gpkg"

    # 1. If user passed a direct standalone .gpkg containing a 'grid' layer, honor it directly
    if (
        path.is_file()
        and path.suffix.lower() == ".gpkg"
        and path.name not in ("catalog.gpkg", "roi.gpkg")
        and _gpkg_has_grid_layer(path)
        and not overwrite
        and not _is_grid_stale(path, ws_dir, tile_size=tile_size, buffer_size=buffer_size)
    ):
        gpkg_path = path
    elif hive_gpkg.exists() and not overwrite and not _is_grid_stale(hive_gpkg, ws_dir, tile_size=tile_size, buffer_size=buffer_size):
        gpkg_path = hive_gpkg
    elif (
        primary_gpkg.exists()
        and not overwrite
        and not _is_grid_stale(primary_gpkg, ws_dir, tile_size=tile_size, buffer_size=buffer_size)
        and (not (ws_dir / "catalog" / "catalog.gpkg").exists() or (tile_size == 1200 and buffer_size == 30))
    ):
        gpkg_path = primary_gpkg
    else:
        logger.info(f"Building grid index (tile_size={tile_size}m, buffer={buffer_size}m, overwrite={overwrite})...")
        build_target = path if (path.is_file() and path.suffix.lower() == ".gpkg" and not (ws_dir / "catalog" / "catalog.gpkg").exists()) else ws_dir
        grid_gdf, crs_str = build_workspace_grid(build_target, tile_size=tile_size, buffer_size=buffer_size, overwrite=overwrite)
        gpkg_path = ws_dir / "catalog" / "grids" / f"tilesize={tile_size}" / f"buffer={buffer_size}" / "grid.gpkg"
        if not gpkg_path.exists():
            gpkg_path = primary_gpkg

    sql_query = f"SELECT * FROM grid WHERE tile_id = {base_id}"
    try:
        single_row_gdf = pyogrio.read_dataframe(gpkg_path, sql=sql_query)
    except Exception as e:
        raise GridError(f"Failed to query tile_id {base_id} from {gpkg_path}: {e}")

    if single_row_gdf.empty:
        raise GridError(f"Tile ID {base_id} not found in {gpkg_path}")

    row = single_row_gdf.iloc[0]
    layer_crs: str = single_row_gdf.crs.to_string() if single_row_gdf.crs else "EPSG:4326"
    row_grid_crs = str(row.get("grid_crs") or "").strip() if ("grid_crs" in row and pd.notna(row.get("grid_crs"))) else ""
    grid_crs: str = row_grid_crs if row_grid_crs else layer_crs

    # Recover core polygon in the tile's metric grid_crs
    if "core_wkt" in row and isinstance(row["core_wkt"], str) and row["core_wkt"].strip():
        core_poly: Polygon = wkt_loads(row["core_wkt"])
    elif "core_minx" in row and pd.notna(row.get("core_minx")) and pd.notna(row.get("core_maxx")):
        core_poly = box(
            float(row["core_minx"]),
            float(row["core_miny"]),
            float(row["core_maxx"]),
            float(row["core_maxy"]),
        )
    elif grid_crs != layer_crs and row.geometry is not None:
        core_poly = gpd.GeoSeries([row.geometry], crs=layer_crs).to_crs(grid_crs).iloc[0]
    else:
        core_poly = row.geometry

    # Recover buffered polygon in the tile's metric grid_crs
    if "buffered_wkt" in row and isinstance(row["buffered_wkt"], str) and row["buffered_wkt"].strip():
        buffered_poly = wkt_loads(row["buffered_wkt"])
    else:
        cb0, cb1, cb2, cb3 = core_poly.bounds
        buffered_poly = box(cb0 - float(buffer_size), cb1 - float(buffer_size), cb2 + float(buffer_size), cb3 + float(buffer_size))

    b_minx, b_miny, b_maxx, b_maxy = buffered_poly.bounds
    buffered_bounds_str = row.get("buffered_bounds_str") or f"([{b_minx}, {b_maxx}], [{b_miny}, {b_maxy}])"

    c_minx, c_miny, c_maxx, c_maxy = core_poly.bounds
    core_bounds_str = row.get("core_bounds_str") or f"([{c_minx}, {c_maxx}], [{c_miny}, {c_maxy}])"

    # Handle hierarchical quadrant subdivision if quadrant tokens are present
    nom_tile_size = int(row.get("tile_size") or tile_size)
    nom_buffer_size = int(row.get("buffer_size") or buffer_size)
    cur_core_poly = core_poly
    cur_tile_size = float(nom_tile_size)
    cur_buffer_size = float(nom_buffer_size)

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

    # Parse URLs from source_urls or source_url column
    urls: List[str] = []
    if "source_urls" in row and isinstance(row["source_urls"], str) and row["source_urls"].strip():
        try:
            parsed = json.loads(row["source_urls"])
            if isinstance(parsed, list):
                urls = [str(u) for u in parsed if u]
        except Exception:
            urls = [str(row["source_urls"])]
    if not urls and "source_url" in row and pd.notna(row.get("source_url")) and str(row.get("source_url")).strip():
        urls = [str(row["source_url"]).strip()]

    additional_metadata: Dict[str, Any] = {}
    if "additional_metadata_json" in row and isinstance(row["additional_metadata_json"], str):
        try:
            additional_metadata = json.loads(row["additional_metadata_json"])
        except Exception:
            additional_metadata = {}

    dataset_id = str(row.get("dataset_id") or "")
    provider = str(row.get("provider") or "")
    name_str = str(row.get("name") or "")
    raw_date = str(row.get("date") or row.get("collect_end") or "2022")
    year = str(row.get("year") or row.get("collect_year") or raw_date[:4])
    state = str(row.get("state") or row.get("state_abbr") or "CA")

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

    c_b = core_poly.bounds
    core_minx = round(float(c_b[0]), 2)
    core_miny = round(float(c_b[1]), 2)
    core_maxx = round(float(c_b[2]), 2)
    core_maxy = round(float(c_b[3]), 2)

    ul_e_str = format_coord(core_minx)
    ul_n_str = format_coord(core_maxy)

    tile_basename = f"{dataset_id}_tile_E{ul_e_str}_N{ul_n_str}{quadrant_suffix}"
    hive_dir = f"provider={provider}/dataset={dataset_id}/tilesize={nom_tile_size}/buffer={nom_buffer_size}"
    hive_path = f"{hive_dir}/{tile_basename}"

    crop_bbox = [core_minx, core_miny, core_maxx, core_maxy]
    crop_pdal_bounds = f"([{core_minx}, {core_maxx}], [{core_miny}, {core_maxy}])"
    crop_gdal_te = f"{core_minx} {core_miny} {core_maxx} {core_maxy}"

    raw_dens = row.get("point_density")
    density = float(raw_dens) if (raw_dens is not None and not (isinstance(raw_dens, float) and math.isnan(raw_dens))) else 10.0
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
    Returns the filesystem path to the Hive-partitioned grid.gpkg (or direct standalone grid GeoPackage)
    for given tile and buffer size.
    """
    p = Path(workspace_or_manifest)
    if (
        p.is_file()
        and p.suffix.lower() == ".gpkg"
        and p.name not in ("catalog.gpkg", "roi.gpkg")
        and _gpkg_has_grid_layer(p)
    ):
        return p

    ws = p
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
    Lazily generates or refreshes the grid if not present on disk, if stale after a catalog update, or if overwrite=True.
    """
    p = Path(workspace_or_manifest)
    ws_dir = (p.parent.parent if p.parent.name == "catalog" else p.parent) if (p.name == "manifest.json" or p.suffix.lower() == ".gpkg") else p

    grid_path = get_grid_path(workspace_or_manifest, tile_size=tile_size, buffer_size=buffer_size)
    if not grid_path.exists() or overwrite or _is_grid_stale(grid_path, ws_dir, tile_size=tile_size, buffer_size=buffer_size):
        build_workspace_grid(workspace_or_manifest, tile_size=tile_size, buffer_size=buffer_size, overwrite=True)
        grid_path = get_grid_path(workspace_or_manifest, tile_size=tile_size, buffer_size=buffer_size)
    if _gpkg_has_grid_layer(grid_path):
        return gpd.read_file(grid_path, layer="grid")
    return gpd.read_file(grid_path)

