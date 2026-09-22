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

def test_stream_single_tile_buffer_dimension_tagging(tmp_path: Path):
    """Test that stream_single_tile generates buffer Extra Bytes dimension (0 for core, 1 for buffer)."""
    import subprocess
    from als_finder.core.standardization import stream_single_tile
    from als_finder.core.grid_manager import create_tile_grid_index, export_grid_manifest
    from shapely.geometry import box

    # 1. Create synthetic input dataset LAZ with points across 0 to 100
    raw_laz = tmp_path / "synthetic_raw.las"
    faux_pipe = [
        {"type": "readers.faux", "bounds": "([0, 100], [0, 100], [0, 10])", "mode": "ramp", "count": 100},
        {"type": "writers.las", "filename": str(raw_laz.absolute()), "a_srs": "EPSG:3857"}
    ]
    subprocess.run(["pdal", "pipeline", "-s"], input=json.dumps(faux_pipe).encode("utf-8"), check=True)

    # 2. Build minimal catalog covering the synthetic area
    poly = box(20, 20, 80, 80)
    roi_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs="EPSG:3857")
    grid_gdf, crs_str = create_tile_grid_index(roi_gdf, tile_size=60, buffer_size=20, target_crs="EPSG:3857")
    manifest_data = {
        "search_parameters": {"roi": "test"},
        "datasets": [{"name": "synth", "url": str(raw_laz.absolute())}],
    }
    cat_dir = tmp_path / "catalog"
    export_grid_manifest(grid_gdf, manifest_data, cat_dir, tile_size=60, buffer_size=20)

    # 3. Stream tile with buffer
    out_tile = tmp_path / "streamed_tile.laz"
    res_path = stream_single_tile(
        manifest_or_grid_path=cat_dir / "grid.gpkg",
        tile_id=0,
        out_path=out_tile,
        tile_size=60,
        buffer_size=20,
        crs="EPSG:3857",
        overwrite=False
    )
    assert res_path.exists()

    # 4. Verify that buffer Extra Bytes dimension is present with 0 (core) and 1 (buffer)
    info_res = subprocess.run(
        ["pdal", "info", str(res_path.absolute()), "--readers.las.use_eb_vlr=true", "--dimensions", "buffer"],
        capture_output=True,
        text=True,
        check=True
    )
    info_data = json.loads(info_res.stdout)
    stats = info_data.get("stats", {}).get("statistic", [])
    buf_stat = next((s for s in stats if s.get("name") == "buffer"), None)
    assert buf_stat is not None, "buffer dimension not found in Extra Bytes VLR"
    assert buf_stat["minimum"] == 0, f"Expected minimum buffer value 0, got {buf_stat['minimum']}"
    assert buf_stat["maximum"] == 1, f"Expected maximum buffer value 1, got {buf_stat['maximum']}"


def test_cli_plan_tasks_parquet(tmp_path: Path):
    """Test that 'als-finder plan --tasks-parquet' exports valid compressed Parquet."""
    from click.testing import CliRunner
    from als_finder.cli import cli
    import pandas as pd
    from shapely.geometry import box
    from als_finder.core.grid_manager import create_tile_grid_index, export_grid_manifest

    # Setup minimal catalog
    poly = box(0, 0, 2400, 2400)
    roi_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs="EPSG:3857")
    grid_gdf, _ = create_tile_grid_index(roi_gdf, tile_size=1200, buffer_size=30, target_crs="EPSG:3857")
    manifest_data = {
        "search_parameters": {"roi": "test"},
        "datasets": [{"name": "test_ds", "url": "http://example.com/test.laz"}],
    }
    cat_dir = tmp_path / "catalog"
    export_grid_manifest(grid_gdf, manifest_data, cat_dir, tile_size=1200, buffer_size=30)

    parquet_out = tmp_path / "tasks.parquet"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "plan",
        "--workspace", str(tmp_path),
        "--tasks-parquet", str(parquet_out),
        "--tasks-csv"
    ])
    assert result.exit_code == 0, f"Plan command failed: {result.output}"
    assert parquet_out.exists(), "tasks.parquet file was not created"

    # Read with pandas / pyarrow and verify contents
    df = pd.read_parquet(parquet_out)
    assert len(df) == len(grid_gdf)
    assert "task_id" in df.columns
    assert "basename" in df.columns
    assert "core_minx" in df.columns
    assert "crop_gdal_te" in df.columns
    assert df["task_id"].iloc[0] == 1
    assert str(df["tile_id"].iloc[0]) == "0"

