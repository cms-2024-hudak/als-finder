"""
Unit test suite for als_finder.core.grid_manager.
"""

import json
from pathlib import Path
import geopandas as gpd
import pytest
from shapely.geometry import box, Polygon

from als_finder.core.grid_manager import (
    GridError,
    create_tile_grid_index,
    export_grid_manifest,
    get_tile_spec,
    resolve_projected_crs,
)


@pytest.fixture
def sample_roi_gdf() -> gpd.GeoDataFrame:
    """Returns a sample GeoDataFrame representing a 1km x 1km region in Oregon (WGS84)."""
    # Centered around Lake Tahoe / Oregon bounds
    poly = box(-122.5, 44.0, -122.48, 44.02)
    return gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs="EPSG:4326")


def test_resolve_projected_crs_auto(sample_roi_gdf: gpd.GeoDataFrame):
    """Test auto-detection of local UTM zone."""
    crs_str = resolve_projected_crs(sample_roi_gdf, target_crs=None)
    assert crs_str.startswith("EPSG:")
    # Oregon bounds (-122.5W) should resolve to UTM Zone 10N (EPSG:32610)
    assert crs_str == "EPSG:32610"


def test_resolve_projected_crs_explicit(sample_roi_gdf: gpd.GeoDataFrame):
    """Test explicit user-specified projected CRS."""
    crs_str = resolve_projected_crs(sample_roi_gdf, target_crs="EPSG:3857")
    assert crs_str == "EPSG:3857"


def test_create_tile_grid_index_valid(sample_roi_gdf: gpd.GeoDataFrame):
    """Test valid grid tile generation."""
    grid_gdf, crs_str = create_tile_grid_index(
        sample_roi_gdf, tile_size=500, buffer_size=30, target_crs="EPSG:3857"
    )
    assert crs_str == "EPSG:3857"
    assert not grid_gdf.empty
    assert "tile_id" in grid_gdf.columns
    assert "buffered_geometry" in grid_gdf.columns
    assert grid_gdf.crs.to_string() == "EPSG:3857"

    # Verify tile bounds math
    first_tile = grid_gdf.iloc[0]
    core_poly: Polygon = first_tile.geometry
    buffered_poly: Polygon = first_tile.buffered_geometry

    c_minx, c_miny, c_maxx, c_maxy = core_poly.bounds
    b_minx, b_miny, b_maxx, b_maxy = buffered_poly.bounds

    # Core tile size should be 500m
    assert abs((c_maxx - c_minx) - 500) < 1e-3
    assert abs((c_maxy - c_miny) - 500) < 1e-3

    # Buffered tile should extend 30m on each side
    assert abs((b_minx - (c_minx - 30))) < 1e-3
    assert abs((b_maxx - (c_maxx + 30))) < 1e-3


def test_create_tile_grid_index_invalid_args(sample_roi_gdf: gpd.GeoDataFrame):
    """Test fail-fast validation for invalid tile/buffer inputs."""
    with pytest.raises(GridError):
        create_tile_grid_index(sample_roi_gdf, tile_size=0)

    with pytest.raises(GridError):
        create_tile_grid_index(sample_roi_gdf, buffer_size=-10)

    with pytest.raises(GridError):
        create_tile_grid_index(gpd.GeoDataFrame())


def test_export_grid_manifest_and_get_tile_spec(
    sample_roi_gdf: gpd.GeoDataFrame, tmp_path: Path
):
    """Test chunked export to grid.gpkg and zero-copy single-row SQL tile lookup."""
    grid_gdf, crs_str = create_tile_grid_index(
        sample_roi_gdf, tile_size=500, buffer_size=30, target_crs="EPSG:3857"
    )
    manifest_data = {
        "search_parameters": {"roi": "test"},
        "datasets": [{"name": "test_dataset", "url": "https://example.com/test.copc.laz"}],
    }

    gpkg_path, manifest_path = export_grid_manifest(
        grid_gdf, manifest_data, tmp_path, batch_size=2
    )

    assert gpkg_path.exists()
    assert manifest_path.exists()

    # Query single tile spec via get_tile_spec
    tile_spec = get_tile_spec(tmp_path, tile_id=0)

    assert tile_spec["tile_id"] == 0
    assert tile_spec["grid_crs"] == "EPSG:3857"
    assert isinstance(tile_spec["core_poly"], Polygon)
    assert isinstance(tile_spec["buffered_poly"], Polygon)
    assert "https://example.com/test.copc.laz" in tile_spec["urls"]
