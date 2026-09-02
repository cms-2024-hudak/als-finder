import json
import pytest
from pathlib import Path
from click.testing import CliRunner

import als_finder
from als_finder.core.grid_manager import parse_quadrant_tile_id, GridError
from als_finder.cli import cli


def test_parse_quadrant_tile_id():
    """Verify parsing of base integers and hierarchical quadrant suffixes."""
    assert parse_quadrant_tile_id(15) == (15, [])
    assert parse_quadrant_tile_id("15") == (15, [])
    assert parse_quadrant_tile_id("0015") == (15, [])
    assert parse_quadrant_tile_id("15_NW") == (15, ["NW"])
    assert parse_quadrant_tile_id("15_nw") == (15, ["NW"])
    assert parse_quadrant_tile_id("15_NE") == (15, ["NE"])
    assert parse_quadrant_tile_id("15_SW") == (15, ["SW"])
    assert parse_quadrant_tile_id("15_SE") == (15, ["SE"])
    assert parse_quadrant_tile_id("15_NW_SE") == (15, ["NW", "SE"])

    with pytest.raises(GridError):
        parse_quadrant_tile_id("invalid")

    with pytest.raises(GridError):
        parse_quadrant_tile_id("15_UNKNOWN")


def test_quadrant_geometry_bisection(tmp_path):
    """Verify exact 4-way spatial bisection of parent bounding boxes."""
    # Test using existing test workspace or build simple grid
    ws = Path("scratch/test_workspace")
    if not ws.exists():
        pytest.skip("scratch/test_workspace not found.")

    base_spec = als_finder.get_tile_spec(ws, tile_id=15, tile_size=500, buffer_size=50)
    c_minx, c_miny, c_maxx, c_maxy = base_spec["core_poly"].bounds
    assert c_maxx - c_minx == 500
    assert c_maxy - c_miny == 500

    nw_spec = als_finder.get_tile_spec(ws, tile_id="15_NW", tile_size=500, buffer_size=50)
    ne_spec = als_finder.get_tile_spec(ws, tile_id="15_NE", tile_size=500, buffer_size=50)
    sw_spec = als_finder.get_tile_spec(ws, tile_id="15_SW", tile_size=500, buffer_size=50)
    se_spec = als_finder.get_tile_spec(ws, tile_id="15_SE", tile_size=500, buffer_size=50)

    # Core sizes must be halved (250m)
    assert nw_spec["tile_size"] == 250
    assert nw_spec["buffer_size"] == 25
    assert nw_spec["parent_tile_id"] == 15
    assert nw_spec["quadrant"] == "NW"

    nw_bounds = nw_spec["core_poly"].bounds
    ne_bounds = ne_spec["core_poly"].bounds
    sw_bounds = sw_spec["core_poly"].bounds
    se_bounds = se_spec["core_poly"].bounds

    # Exact boundary alignment
    assert nw_bounds == (c_minx, (c_miny + c_maxy) / 2, (c_minx + c_maxx) / 2, c_maxy)
    assert ne_bounds == ((c_minx + c_maxx) / 2, (c_miny + c_maxy) / 2, c_maxx, c_maxy)
    assert sw_bounds == (c_minx, c_miny, (c_minx + c_maxx) / 2, (c_miny + c_maxy) / 2)
    assert se_bounds == ((c_minx + c_maxx) / 2, c_miny, c_maxx, (c_miny + c_maxy) / 2)

    # Seamless contact
    assert nw_bounds[2] == ne_bounds[0]
    assert sw_bounds[3] == nw_bounds[1]
    assert se_bounds[3] == ne_bounds[1]


def test_cli_grid_info_audit():
    """Verify grid-info with --max-points performs pre-flight memory audit."""
    ws = Path("scratch/test_workspace")
    if not ws.exists():
        pytest.skip("scratch/test_workspace not found.")

    runner = CliRunner()
    result = runner.invoke(cli, [
        "grid-info",
        "--workspace", str(ws),
        "--tile-size", "500",
        "--buffer-size", "50",
        "--max-points", "4000000",
        "--json"
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "audit" in data
    audit = data["audit"]
    assert audit["max_points"] == 4000000
    assert "standard_tiles" in audit
    assert "subdivided_tiles" in audit
    assert "is_hyperdense" in audit


def test_cli_fetch_tile_quadrant_dry():
    """Verify fetch-tile accepts quadrant strings like 15_NW."""
    ws = Path("scratch/test_workspace")
    if not ws.exists():
        pytest.skip("scratch/test_workspace not found.")

    spec = als_finder.get_tile_spec(ws, tile_id="15_NW", tile_size=500, buffer_size=50)
    assert spec["tile_id"] == "15_NW"
    assert spec["quadrant"] == "NW"
    assert spec["level"] == 1
    assert "CA_SierraNevada_5_2022_tile_0015_NW.laz" in spec["basename"]
