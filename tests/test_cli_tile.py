"""
Unit test suite for als_finder CLI fetch-tile and grid-info commands.
"""

import json
from pathlib import Path
import geopandas as gpd
from click.testing import CliRunner
import pytest

from als_finder.cli import cli
from als_finder.core.grid_manager import create_tile_grid_index, export_grid_manifest


@pytest.fixture
def sample_workspace(tmp_path: Path) -> Path:
    """Creates a temporary workspace catalog directory with a valid grid.gpkg and manifest.json."""
    from shapely.geometry import box
    poly = box(-122.5, 44.0, -122.48, 44.02)
    sample_roi = gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs="EPSG:4326")
    
    grid_gdf, crs_str = create_tile_grid_index(sample_roi, tile_size=500, buffer_size=30, target_crs="EPSG:3857")
    manifest_data = {
        "search_parameters": {"roi": "test"},
        "datasets": [{"name": "test_dataset", "url": "https://example.com/test.copc.laz"}],
    }
    
    cat_dir = tmp_path / "catalog"
    export_grid_manifest(grid_gdf, manifest_data, cat_dir)
    return cat_dir


def test_cli_grid_info(sample_workspace: Path):
    """Test als-finder grid-info CLI command with --json flag."""
    runner = CliRunner()
    manifest_path = sample_workspace / "manifest.json"
    result = runner.invoke(cli, ["grid-info", "--manifest", str(manifest_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "success"
    assert data["grid_crs"] == "EPSG:3857"
    assert "sample_tile_bounds" in data


def test_cli_fetch_tile_help():
    """Test als-finder fetch-tile --help CLI output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["fetch-tile", "--help"])
    assert result.exit_code == 0
    assert "Stream a single spatial core + buffered tile" in result.output


def test_stream_single_tile_directory_hive_resolution(sample_workspace: Path, tmp_path: Path):
    """Test that stream_single_tile auto-resolves directory outputs using Hive partitioning."""
    from als_finder.core.grid_manager import get_tile_spec

    manifest_path = sample_workspace / "manifest.json"
    spec = get_tile_spec(manifest_path, tile_id=0, tile_size=500, buffer_size=30)
    assert "provider=" in spec["hive_path"]
    assert "dataset=" in spec["hive_path"]
    assert spec["basename"].startswith("test_dataset_tile_E")
    assert "_N" in spec["basename"]
    assert "hive_dir" in spec
    assert "crop_pdal_bounds" in spec
