"""
Unit and integration tests for als-finder Sprint 02.5:
1. Stale catalog artifact invalidation on fresh `search` and `update`.
2. `workspace update` provider list parsing (`--provider USGS_EPT,NOAA_STAC`, `--provider all`) and filter overrides (`--doy`, `--roi`).
3. Single-pass MultiPolygon search across providers and phenology `--doy START:END` filtering.
4. Multi-UTM 1:1 sample plot grid generation without continental mesh explosion or 1800m grid shifting.
5. Direct `--manifest sample_tiles.gpkg` support in `get_tile_spec` and `plan --no-subtiles --tasks-csv`.
6. Multi-UTM `fetch tile <id> --no-subtiles` PDAL pipeline generation with per-tile UTM CRS and EPT bounds projection.
"""

import csv
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pytest
from click.testing import CliRunner
from shapely.geometry import MultiPolygon, Polygon, box, mapping

from als_finder.cli import cli
from als_finder.core.grid_manager import (
    build_workspace_grid,
    create_tile_grid_index,
    export_grid_manifest,
    get_tile_spec,
    invalidate_derived_catalog_artifacts,
    read_grid,
)
from als_finder.providers import get_active_providers


def _make_sample_plot_wgs84(lon_center: float, lat_center: float, utm_epsg: str, size_m: float = 1800.0) -> Polygon:
    """Create an exact 1800m x 1800m UTM box aligned to 30m LANDFIRE grid, reprojected to EPSG:4326."""
    pt_gdf = gpd.GeoDataFrame(geometry=[box(lon_center - 0.001, lat_center - 0.001, lon_center + 0.001, lat_center + 0.001)], crs="EPSG:4326")
    pt_utm = pt_gdf.to_crs(utm_epsg)
    cx, cy = pt_utm.geometry.iloc[0].centroid.x, pt_utm.geometry.iloc[0].centroid.y
    # Align to 30m LANDFIRE pixel edge (intentionally NOT aligned to 1800m multiples)
    minx = round(cx / 30.0) * 30.0 + 30.0
    miny = round(cy / 30.0) * 30.0 + 30.0
    utm_box = box(minx, miny, minx + size_m, miny + size_m)
    wgs_gdf = gpd.GeoDataFrame(geometry=[utm_box], crs=utm_epsg).to_crs("EPSG:4326")
    return wgs_gdf.geometry.iloc[0], utm_box


def test_get_active_providers_all_keyword():
    """Verify --provider all and default 6-provider activation."""
    all_provs = get_active_providers(["all"])
    cls_names = {p.__class__.__name__ for p in all_provs}
    assert len(all_provs) == 6
    assert cls_names == {
        "USGSProvider",
        "NOAAProvider",
        "OpenTopographyProvider",
        "NEONProvider",
        "GLiHTProvider",
        "EarthdataProvider",
    }


def test_search_and_update_invalidate_stale_grid_and_fetch_array(tmp_path: Path):
    """
    Verify that running a fresh `search` or `update` invalidates stale `grid.gpkg`,
    `grids/tilesize=*/buffer=*/grid.gpkg`, and `fetch_array.csv` so `plan` and `fetch tile`
    never serve outdated tiles from a prior search.
    """
    ws_dir = tmp_path / "ws"
    cat_dir = ws_dir / "catalog"
    stale_subgrid = cat_dir / "grids" / "tilesize=1800" / "buffer=30"
    stale_subgrid.mkdir(parents=True, exist_ok=True)

    # Create dummy stale artifacts
    stale_grid_gpkg = cat_dir / "grid.gpkg"
    stale_Param_gpkg = stale_subgrid / "grid.gpkg"
    stale_fetch_csv = cat_dir / "fetch_array.csv"
    stale_grid_gpkg.write_text("stale")
    stale_Param_gpkg.write_text("stale")
    stale_fetch_csv.write_text("stale")

    removed = invalidate_derived_catalog_artifacts(cat_dir)
    assert len(removed) >= 3
    assert not stale_grid_gpkg.exists()
    assert not stale_Param_gpkg.exists()
    assert not stale_fetch_csv.exists()


def test_workspace_update_provider_parsing_and_filter_overrides(tmp_path: Path):
    """
    Verify `als-finder workspace update --provider USGS_EPT` does NOT split 'USGS_EPT' into
    single characters ['U','S','G','S','_','E','P','T'] and properly applies `--doy` and `--roi`.
    """
    ws_dir = tmp_path / "ws_update"
    cat_dir = ws_dir / "catalog"
    cat_dir.mkdir(parents=True, exist_ok=True)

    roi_poly, _ = _make_sample_plot_wgs84(-105.5, 40.0, "EPSG:32613", 1800.0)
    roi_path = tmp_path / "roi.gpkg"
    gpd.GeoDataFrame({"sample_id": [0]}, geometry=[roi_poly], crs="EPSG:4326").to_file(roi_path, driver="GPKG")

    manifest_file = cat_dir / "manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "search_parameters": {
                    "roi": str(roi_path),
                    "bbox": None,
                    "name": None,
                    "date": None,
                    "doy": None,
                    "density": None,
                    "providers": ["USGS_EPT"],
                },
                "total_found": 0,
                "datasets": [],
            }
        )
    )

    fake_ds = {
        "provider": "USGS_EPT",
        "dataset_id": "CO_Test_2020",
        "name": "CO_Test_2020",
        "url": "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/CO_Test_2020/ept.json",
        "date": "2020-07-15",
        "srs": "EPSG:3857",
        "bounds": list(roi_poly.bounds),
        "geometry": mapping(roi_poly),
        "point_count": 50000000,
        "point_density": 15.0,
        "area_sqkm": 3.24,
    }

    mock_prov = MagicMock()
    mock_prov.name = "USGS_EPT"
    mock_prov.search.return_value = [fake_ds]

    runner = CliRunner()
    with patch("als_finder.cli.get_active_providers", return_value=[mock_prov]) as mock_get_provs:
        res = runner.invoke(
            cli,
            [
                "workspace",
                "update",
                "--workspace",
                str(ws_dir),
                "--provider",
                "USGS_EPT",
                "--doy",
                "121:273",
            ],
        )
        assert res.exit_code == 0, res.output
        called_providers = mock_get_provs.call_args[0][0]
        assert called_providers == ["USGS_EPT"]

    updated_manifest = json.loads(manifest_file.read_text())
    assert updated_manifest["search_parameters"]["providers"] == ["USGS_EPT"]
    assert updated_manifest["search_parameters"]["doy"] == "121:273"
    assert len(updated_manifest["datasets"]) == 1
    assert updated_manifest["datasets"][0]["dataset_id"] == "CO_Test_2020"


def test_multi_polygon_search_single_pass_and_doy_filter(tmp_path: Path):
    """
    Verify that passing a multi-polygon GeoPackage to `als-finder search` executes a single-pass
    MultiPolygon query and filters acquisitions by day-of-year (`--doy 121:273`) across any year.
    """
    poly1, _ = _make_sample_plot_wgs84(-121.5, 44.0, "EPSG:32610", 1800.0)
    poly2, _ = _make_sample_plot_wgs84(-105.5, 40.0, "EPSG:32613", 1800.0)
    roi_path = tmp_path / "multi_plots.gpkg"
    gpd.GeoDataFrame(
        {"sample_id": [0, 1]},
        geometry=[poly1, poly2],
        crs="EPSG:4326",
    ).to_file(roi_path, driver="GPKG")

    leaf_on_ds = {
        "provider": "USGS_EPT",
        "dataset_id": "OR_LeafOn_2019",
        "name": "OR_LeafOn_2019",
        "url": "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/OR_LeafOn_2019/ept.json",
        "date": "2019-06-20",  # DOY 171 (inside 121:273)
        "srs": "EPSG:3857",
        "bounds": list(poly1.bounds),
        "geometry": mapping(poly1),
        "point_count": 40000000,
        "point_density": 12.0,
        "area_sqkm": 3.24,
    }
    leaf_off_ds = {
        "provider": "NOAA_STAC",
        "dataset_id": "CO_LeafOff_2022",
        "name": "CO_LeafOff_2022",
        "url": "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/9999/ept.json",
        "date": "2022-01-15",  # DOY 15 (outside 121:273)
        "srs": "EPSG:3857",
        "bounds": list(poly2.bounds),
        "geometry": mapping(poly2),
        "point_count": 40000000,
        "point_density": 10.0,
        "area_sqkm": 3.24,
    }

    mock_prov = MagicMock()
    mock_prov.name = "USGS_EPT"
    mock_prov.search.return_value = [leaf_on_ds, leaf_off_ds]

    ws_dir = tmp_path / "ws_search"
    runner = CliRunner()
    with patch("als_finder.cli.get_active_providers", return_value=[mock_prov]):
        res = runner.invoke(
            cli,
            [
                "search",
                "--roi",
                str(roi_path),
                "--doy",
                "121:273",
                "--workspace",
                str(ws_dir),
            ],
        )
        assert res.exit_code == 0, res.output
        assert mock_prov.search.call_count == 1
        passed_roi = mock_prov.search.call_args.kwargs["roi"]
        assert isinstance(passed_roi, MultiPolygon)

    manifest_payload = json.loads((ws_dir / "catalog" / "manifest.json").read_text())
    assert len(manifest_payload["datasets"]) == 1
    assert manifest_payload["datasets"][0]["dataset_id"] == "OR_LeafOn_2019"
    assert (ws_dir / "catalog" / "roi.gpkg").exists()


def test_multi_utm_1to1_sample_grid_no_continental_mesh():
    """
    Verify that 3 disjoint 1800m x 1800m sample plots across UTM zones 10N, 13N, and 18N
    produce a strict 1:1 3-tile grid (tile_id = 0, 1, 2) with exact 30m-aligned UTM bounds
    and per-tile `grid_crs`, `core_wkt`, and `buffered_wkt` without building a continental mesh.
    """
    p10_wgs, p10_utm = _make_sample_plot_wgs84(-122.2, 44.2, "EPSG:32610", 1800.0)
    p13_wgs, p13_utm = _make_sample_plot_wgs84(-105.6, 40.1, "EPSG:32613", 1800.0)
    p18_wgs, p18_utm = _make_sample_plot_wgs84(-74.0, 41.5, "EPSG:32618", 1800.0)

    roi_gdf = gpd.GeoDataFrame(
        {
            "sample_id": [0, 1, 2],
            "provider": ["USGS_EPT", "OpenTopography", "NOAA_STAC"],
            "dataset_id": ["OR_West", "CO_FrontRange", "NY_Hudson"],
            "source_url": [
                "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/OR_West/ept.json",
                "https://opentopography.s3.sdsc.edu/pc-bulk/CO_FrontRange/ept.json",
                "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/1234/ept.json",
            ],
            "point_density": [14.5, 22.0, 8.0],
        },
        geometry=[p10_wgs, p13_wgs, p18_wgs],
        crs="EPSG:4326",
    )

    grid_gdf, crs_str = create_tile_grid_index(roi_gdf, tile_size=1800, buffer_size=30)
    assert len(grid_gdf) == 3
    assert list(grid_gdf["tile_id"]) == [0, 1, 2]
    assert list(grid_gdf["grid_crs"]) == ["EPSG:32610", "EPSG:32613", "EPSG:32618"]

    # Verify exact metric bounds match the original 30m-aligned UTM boxes (not re-snapped to 1800m multiples)
    from shapely.wkt import loads as wkt_loads

    for idx, expected_utm in enumerate([p10_utm, p13_utm, p18_utm]):
        core_poly = wkt_loads(grid_gdf.iloc[idx]["core_wkt"])
        buf_poly = wkt_loads(grid_gdf.iloc[idx]["buffered_wkt"])
        for a, b in zip(core_poly.bounds, expected_utm.bounds):
            assert abs(a - b) < 0.05
        assert abs((buf_poly.bounds[2] - buf_poly.bounds[0]) - 1860.0) < 0.05


def test_get_tile_spec_and_plan_direct_gpkg_multi_utm(tmp_path: Path):
    """
    Verify passing a multi-UTM sample GeoPackage directly via `--manifest sample_tiles.gpkg`
    to `get_tile_spec` and `als-finder plan --no-subtiles --tasks-csv`.
    """
    p10_wgs, p10_utm = _make_sample_plot_wgs84(-122.2, 44.2, "EPSG:32610", 1800.0)
    p13_wgs, p13_utm = _make_sample_plot_wgs84(-105.6, 40.1, "EPSG:32613", 1800.0)

    roi_gdf = gpd.GeoDataFrame(
        {
            "sample_id": [0, 1],
            "provider": ["USGS_EPT", "NOAA_STAC"],
            "dataset_id": ["OR_West", "CO_FrontRange"],
            "source_url": [
                "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/OR_West/ept.json",
                "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/1234/ept.json",
            ],
            "point_density": [30.0, 25.0],
        },
        geometry=[p10_wgs, p13_wgs],
        crs="EPSG:4326",
    )

    sample_gpkg = tmp_path / "csu_sample_test.gpkg"
    roi_gdf.to_file(sample_gpkg, layer="sample_tiles_core_1800m", driver="GPKG")

    # 1. Verify get_tile_spec directly on sample_gpkg (auto-builds grid from sample layer)
    spec0 = get_tile_spec(sample_gpkg, tile_id=0, tile_size=1800, buffer_size=30)
    spec1 = get_tile_spec(sample_gpkg, tile_id=1, tile_size=1800, buffer_size=30)

    assert spec0["grid_crs"] == "EPSG:32610"
    assert spec0["provider"] == "USGS_EPT"
    assert spec0["dataset_id"] == "OR_West"
    assert abs(spec0["crop_maxx"] - spec0["crop_minx"] - 1800.0) < 0.05

    assert spec1["grid_crs"] == "EPSG:32613"
    assert spec1["provider"] == "NOAA_STAC"
    assert spec1["dataset_id"] == "CO_FrontRange"
    assert abs(spec1["crop_maxx"] - spec1["crop_minx"] - 1800.0) < 0.05

    # 2. Verify CLI `plan --manifest sample_gpkg -s 1800 -b 30 --no-subtiles --tasks-csv`
    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            "plan",
            "--manifest",
            str(sample_gpkg),
            "-s",
            "1800",
            "-b",
            "30",
            "--no-subtiles",
            "--tasks-csv",
        ],
    )
    assert res.exit_code == 0, res.output
    rows = list(csv.DictReader(io.StringIO(res.output)))
    assert len(rows) == 2
    assert rows[0]["tile_id"] == "0"
    assert rows[0]["grid_crs"] == "EPSG:32610"
    assert rows[0]["provider"] == "USGS_EPT"
    assert rows[1]["tile_id"] == "1"
    assert rows[1]["grid_crs"] == "EPSG:32613"
    assert rows[1]["provider"] == "NOAA_STAC"
    assert abs(float(rows[1]["core_maxx"]) - float(rows[1]["core_minx"]) - 1800.0) < 0.05


def test_fetch_tile_no_subtiles_multi_utm_pdal_pipeline(tmp_path: Path):
    """
    Verify `als-finder fetch tile 1 -s 1800 -b 30 --no-subtiles` does not subdivide even
    when point density exceeds budget, and constructs a PDAL pipeline with the tile's local
    UTM CRS (`EPSG:32613`) and Web Mercator (`EPSG:3857`) EPT reader bounds.
    """
    p10_wgs, _ = _make_sample_plot_wgs84(-122.2, 44.2, "EPSG:32610", 1800.0)
    p13_wgs, _ = _make_sample_plot_wgs84(-105.6, 40.1, "EPSG:32613", 1800.0)

    roi_gdf = gpd.GeoDataFrame(
        {
            "sample_id": [0, 1],
            "provider": ["USGS_EPT", "NOAA_STAC"],
            "dataset_id": ["OR_West", "CO_FrontRange"],
            "source_url": [
                "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/OR_West/ept.json",
                "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/1234/ept.json",
            ],
            "point_density": [50.0, 50.0],  # 50 pts/m2 * 1860^2 = 173M points (> default budget)
        },
        geometry=[p10_wgs, p13_wgs],
        crs="EPSG:4326",
    )

    grid_gdf, _ = create_tile_grid_index(roi_gdf, tile_size=1800, buffer_size=30)
    cat_dir = tmp_path / "ws" / "catalog"
    gpkg_path, _ = export_grid_manifest(
        grid_gdf,
        {"search_parameters": {}, "datasets": []},
        cat_dir,
        tile_size=1800,
        buffer_size=30,
    )

    out_laz = tmp_path / "tile_1.laz"
    runner = CliRunner()

    with patch("als_finder.core.standardization.execute_with_memory_limit") as mock_pdal:
        def _touch_laz(cmd, stdin_bytes, memory_limit_mb=4096):
            out_laz.parent.mkdir(parents=True, exist_ok=True)
            out_laz.write_bytes(b"LASF_MOCK")
            return True, ""

        mock_pdal.side_effect = _touch_laz

        res = runner.invoke(
            cli,
            [
                "fetch",
                "tile",
                "1",
                "--manifest",
                str(gpkg_path),
                "-s",
                "1800",
                "-b",
                "30",
                "--max-points",
                "50000000",
                "--no-subtiles",
                "-o",
                str(out_laz),
                "--json",
            ],
        )
        assert res.exit_code == 0, res.output
        payload = json.loads(res.output)
        assert payload["status"] == "success"
        assert payload["tile_id"] == 1
        assert payload["grid_crs"] == "EPSG:32613"
        assert payload["provider"] == "NOAA_STAC"
        assert mock_pdal.call_count == 1

        pipeline_stages = json.loads(mock_pdal.call_args[0][1].decode("utf-8"))
        ept_stage = pipeline_stages[0]
        assert ept_stage["type"] == "readers.ept"
        # Bounds passed to readers.ept must be in Web Mercator (EPSG:3857), around -1.175e7 for -105.6W
        assert "-11" in ept_stage["bounds"]
        reproj_stages = [s for s in pipeline_stages if s.get("type") == "filters.reprojection"]
        assert len(reproj_stages) == 1
        assert reproj_stages[0]["out_srs"] == "EPSG:32613"


def test_enrich_grid_prunes_uncovered_and_ranks_by_overlap(tmp_path: Path):
    """
    Verify Issue #70 fixes:
    1. Grid tiles in a regional ROI that do NOT intersect any discovered dataset footprint are
       pruned from `grid.gpkg` instead of falling back to `datasets[0]`.
    2. When multiple datasets intersect a tile, the dataset covering the largest fraction of the
       tile is selected as primary `dataset_id` (even if an edge-grazing dataset came earlier
       in `manifest.json`), and co-intersecting same-provider URLs are retained in `source_urls`.
    """
    # Create a 2-tile ROI in EPSG:4326: West tile (-106.0 to -105.98) covered, East tile (-105.5 to -105.48) uncovered
    west_poly = box(-106.00, 36.00, -105.99, 36.01)
    east_uncovered_poly = box(-105.50, 36.00, -105.49, 36.01)
    roi_gdf = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[west_poly, east_uncovered_poly],
        crs="EPSG:4326",
    )
    grid_gdf, _ = create_tile_grid_index(roi_gdf, tile_size=1200, buffer_size=30)
    assert len(grid_gdf) >= 2

    # Dataset 0 only grazes a tiny sliver on the western edge (-106.05 to -105.9995)
    ds_sliver = {
        "provider": "USGS_EPT",
        "dataset_id": "Sliver_First_2020",
        "name": "Sliver_First_2020",
        "date": "2020-09-01",
        "point_density": 4.0,
        "url": "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/Sliver_First_2020/ept.json",
        "geometry": box(-106.05, 35.99, -105.999, 36.02).__geo_interface__,
    }
    # Dataset 1 covers 95% of the western tile (-105.999 to -105.97)
    ds_dominant = {
        "provider": "USGS_EPT",
        "dataset_id": "Dominant_Second_2018",
        "name": "Dominant_Second_2018",
        "date": "2018-11-10",
        "point_density": 12.5,
        "url": "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/Dominant_Second_2018/ept.json",
        "geometry": box(-105.999, 35.99, -105.97, 36.02).__geo_interface__,
    }

    cat_dir = tmp_path / "catalog"
    gpkg_path, _ = export_grid_manifest(
        grid_gdf,
        {"search_parameters": {}, "datasets": [ds_sliver, ds_dominant]},
        cat_dir,
        tile_size=1200,
        buffer_size=30,
    )

    saved_grid = gpd.read_file(gpkg_path, layer="grid")
    # Uncovered eastern tiles must be pruned
    assert len(saved_grid) < len(grid_gdf)
    # Sequential tile_id 0..N-1
    assert list(saved_grid["tile_id"]) == list(range(len(saved_grid)))
    # The tile covered 95% by Dominant_Second_2018 must get Dominant_Second_2018, not Sliver_First_2020
    assert "Dominant_Second_2018" in set(saved_grid["dataset_id"])


def test_usgs_pdal_reader_multi_url_merge():
    """
    Verify USGSProvider.get_pdal_reader builds multiple `readers.ept` stages + `filters.merge`
    when a seam tile straddles multiple intersecting USGS EPT workunits.
    """
    from als_finder.providers.usgs import USGSProvider

    prov = USGSProvider()
    poly = box(400000, 4000000, 401200, 4001200)
    urls = [
        "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/BlockA/ept.json",
        "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/BlockB/ept.json",
    ]
    stages = prov.get_pdal_reader(urls, poly, poly_crs="EPSG:32613")
    assert len(stages) == 3
    assert stages[0]["type"] == "readers.ept"
    assert stages[0]["filename"] == urls[0]
    assert stages[1]["type"] == "readers.ept"
    assert stages[1]["filename"] == urls[1]
    assert stages[2]["type"] == "filters.merge"
    assert stages[2]["inputs"] == ["ept_reader_0", "ept_reader_1"]


def test_stream_single_tile_rejects_and_cleans_up_empty_tile(tmp_path: Path):
    """
    Verify that when a streamed tile yields 0 points, `stream_single_tile` unlinks the 0-point
    `.laz` file and raises `EmptyTileError`, and `als-finder fetch tile --json` reports
    `status: "empty"` instead of `status: "success"`.
    """
    import laspy
    from als_finder.core.standardization import stream_single_tile, EmptyTileError

    far_poly = box(5000, 5000, 5100, 5100)
    roi_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[far_poly], crs="EPSG:3857")
    grid_gdf, _ = create_tile_grid_index(roi_gdf, tile_size=100, buffer_size=10, target_crs="EPSG:3857")
    cat_dir = tmp_path / "catalog"
    gpkg_path, _ = export_grid_manifest(
        grid_gdf,
        {"search_parameters": {}, "datasets": [{"name": "far_ds", "url": "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/far_ds/ept.json"}]},
        cat_dir,
        tile_size=100,
        buffer_size=10,
    )

    out_empty_las = tmp_path / "should_not_exist.las"

    def _write_zero_point_las(cmd, stdin_bytes, memory_limit_mb=4096):
        out_empty_las.parent.mkdir(parents=True, exist_ok=True)
        empty_las = laspy.create(point_format=6, file_version="1.4")
        empty_las.write(str(out_empty_las))
        return True, ""

    with patch("als_finder.core.standardization.execute_with_memory_limit", side_effect=_write_zero_point_las):
        with pytest.raises(EmptyTileError):
            stream_single_tile(
                manifest_or_grid_path=gpkg_path,
                tile_id=0,
                out_path=out_empty_las,
                tile_size=100,
                buffer_size=10,
                crs="EPSG:3857",
                tile_format="las",
            )
        assert not out_empty_las.exists(), "0-point .las file must be deleted on EmptyTileError"

        # Also verify CLI `als-finder fetch tile 0 --json` returns status="empty" and point_count=0
        runner = CliRunner()
        res = runner.invoke(
            cli,
            [
                "fetch",
                "tile",
                "0",
                "--manifest",
                str(gpkg_path),
                "-s",
                "100",
                "-b",
                "10",
                "--crs",
                "EPSG:3857",
                "--tile-format",
                "las",
                "-o",
                str(out_empty_las),
                "--json",
            ],
        )
        assert res.exit_code == 0, res.output
        payload = json.loads(res.output)
        assert payload["status"] == "empty"
        assert payload["point_count"] == 0
        assert payload["path"] is None
        assert not out_empty_las.exists()


def test_execute_with_memory_limit_isolates_pdal_driver_path(monkeypatch):
    """
    Verify `execute_with_memory_limit` sets `PDAL_DRIVER_PATH` to an isolated empty directory
    by default so PDAL does not scan third-party plugin DLLs (`libpdal_plugin_reader_arrow.dll`
    / `libpdal_plugin_reader_tiledb.so`) that can collide with `r-arrow` / `libarrow.dll`.
    """
    from als_finder.core.standardization import execute_with_memory_limit

    monkeypatch.delenv("PDAL_DRIVER_PATH", raising=False)
    captured_env = {}

    def _fake_run(cmd, input=None, capture_output=True, env=None, check=True):
        captured_env.update(env or {})
        res = MagicMock()
        res.stderr = b""
        return res

    with patch("als_finder.core.standardization.subprocess.run", side_effect=_fake_run):
        ok, _ = execute_with_memory_limit(["pdal", "pipeline", "-s"], b"{}")
        assert ok is True
        assert "PDAL_DRIVER_PATH" in captured_env
        driver_dir = Path(captured_env["PDAL_DRIVER_PATH"])
        assert driver_dir.exists() and driver_dir.is_dir()
        assert list(driver_dir.iterdir()) == []


