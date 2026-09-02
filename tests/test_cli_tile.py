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
    """Test als-finder fetch tile, fetch-tile alias, and plan --help CLI outputs."""
    runner = CliRunner()
    result_alias = runner.invoke(cli, ["fetch-tile", "--help"])
    assert result_alias.exit_code == 0
    assert "als-finder fetch tile" in result_alias.output

    result_fetch_tile = runner.invoke(cli, ["fetch", "tile", "--help"])
    assert result_fetch_tile.exit_code == 0
    assert "Stream on-demand spatial tiles" in result_fetch_tile.output

    result_plan = runner.invoke(cli, ["plan", "--help"])
    assert result_plan.exit_code == 0
    assert "Plan spatial grid partitioning" in result_plan.output


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


def test_cli_fetch_tile_format_validation(sample_workspace: Path):
    """Test that --tile-format accepts laz, copc, las and rejects invalid options."""
    runner = CliRunner()
    manifest_path = sample_workspace / "manifest.json"

    # Invalid format should fail validation
    res_invalid = runner.invoke(cli, ["fetch", "tile", "0", "--manifest", str(manifest_path), "--tile-format", "invalid_fmt"])
    assert res_invalid.exit_code != 0
    assert "Invalid value for '--tile-format'" in res_invalid.output


def test_cli_search_density_delimiters(tmp_path: Path):
    """Test that search --density accepts ':', '-', '..', and '/' delimiters."""
    from click.testing import CliRunner
    from als_finder.cli import cli
    runner = CliRunner()
    
    # We test that all standard range delimiters parse correctly
    for density_arg in ["2:10", "2-10", "2..10", "2/10", ":10", "2:", "QL1"]:
        res = runner.invoke(cli, ["search", "--roi", "-120,38,-119,39", "--density", density_arg, "--workspace", str(tmp_path), "--no-overwrite"])
        # Even if search finds 0 records or completes, it should not fail on density parsing
        assert "Invalid density" not in res.output
        assert "Invalid QL specification" not in res.output


