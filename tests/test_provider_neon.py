import json
import pytest
from shapely.geometry import box
from als_finder.providers import (
    get_provider,
    get_active_providers,
    NEONProvider
)

def test_neon_provider_registration():
    """Verify NEON provider registration and aliases."""
    p1 = get_provider("neon")
    p2 = get_provider("NEON_AOP")
    p3 = get_provider("aop")
    assert isinstance(p1, NEONProvider)
    assert isinstance(p2, NEONProvider)
    assert isinstance(p3, NEONProvider)

def test_neon_spatial_search_wind_river():
    """Verify NEON spatial search intersecting Wind River (WREF)."""
    provider = NEONProvider()
    # ROI covering WREF Wind River WA
    roi = box(-122.00, 45.80, -121.90, 45.90)
    results = provider.search(roi=roi)

    assert len(results) >= 1
    wref_res = results[0]
    assert wref_res["provider"] == "NEON_AOP"
    assert "WREF" in wref_res["dataset_id"]
    assert wref_res["srs"] == "EPSG:32610"
    assert wref_res["point_density"] > 20.0
    assert wref_res["additional_metadata"]["product_id"] == "DP1.30003.001"

    # Verify JSON serialization
    json_str = json.dumps(wref_res)
    assert len(json_str) > 50

def test_neon_search_filters():
    """Verify NEON filtering by name, date, density."""
    provider = NEONProvider()
    
    # Filter by name / site
    sjer_results = provider.search(name="San Joaquin")
    assert len(sjer_results) >= 1
    assert "SJER" in sjer_results[0]["dataset_id"]

    # Filter by date
    results_2021 = provider.search(start_date="2021-01-01", end_date="2021-12-31")
    for r in results_2021:
        assert r["year"] == 2021

def test_neon_pdal_reader():
    """Verify PDAL reader pipeline construction."""
    provider = NEONProvider()
    urls = ["https://data.neonscience.org/api/v0/data/DP1.30003.001/WREF/2022-06/tile.laz"]
    buffered_poly = box(578000, 5072000, 579000, 5073000)

    stages = provider.get_pdal_reader(urls, buffered_poly, poly_crs="EPSG:32610")
    assert len(stages) == 2
    assert stages[0]["type"] == "readers.las"
    assert stages[1]["type"] == "filters.crop"
