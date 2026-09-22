import json
import pytest
from shapely.geometry import box, Polygon
from als_finder.providers import (
    get_provider,
    get_active_providers,
    list_available_providers,
    GLiHTProvider,
    BaseProvider
)

def test_provider_registry_and_aliases():
    """Verify dynamic provider registry registration and aliases."""
    available = list_available_providers()
    assert "NASA_GLIHT" in available
    assert "USGS_EPT" in available
    assert "OPENTOPOGRAPHY" in available
    assert "NOAA_STAC" in available

    # Test alias resolution
    p1 = get_provider("gliht")
    p2 = get_provider("NASA_GLIHT")
    p3 = get_provider("G-LIHT")
    assert isinstance(p1, GLiHTProvider)
    assert isinstance(p2, GLiHTProvider)
    assert isinstance(p3, GLiHTProvider)

    # Test active providers filtering
    active = get_active_providers(["gliht", "usgs", "noaa"])
    assert len(active) == 3
    names = [p.__class__.__name__ for p in active]
    assert "GLiHTProvider" in names
    assert "USGSProvider" in names
    assert "NOAAProvider" in names

def test_gliht_spatial_search_tahoe():
    """Verify spatial search intersecting Tahoe / Sierra G-LiHT flight transect."""
    provider = GLiHTProvider()
    assert provider.check_access() is True

    # ROI covering part of South Lake Tahoe transect
    roi = box(-120.05, 38.92, -119.95, 38.96)
    results = provider.search(roi=roi)

    assert len(results) >= 1
    tahoe_res = results[0]

    assert tahoe_res["provider"] == "NASA_GLIHT"
    assert "TAHOE" in tahoe_res["dataset_id"] or "Sierra" in tahoe_res["name"]
    assert tahoe_res["year"] == 2022
    assert tahoe_res["srs"] == "EPSG:32610"
    assert tahoe_res["point_density"] > 20.0
    assert "url" in tahoe_res and tahoe_res["url"].endswith(".laz")
    assert "bounds" in tahoe_res and len(tahoe_res["bounds"]) == 4
    assert tahoe_res["geometry"]["type"] == "Polygon"

    # Verify JSON serializability of metadata
    json_str = json.dumps(tahoe_res)
    assert len(json_str) > 50

def test_gliht_search_filters():
    """Verify temporal, name, and density filtering."""
    provider = GLiHTProvider()

    # Name filter
    wref_results = provider.search(name="Wind River")
    assert len(wref_results) == 1
    assert wref_results[0]["dataset_id"] == "GLIHT_WREF_20210622_FL01"

    # Date filter
    results_2020 = provider.search(start_date="2020-01-01", end_date="2020-12-31")
    assert len(results_2020) == 1
    assert results_2020[0]["dataset_id"] == "GLIHT_HARV_20200814_FL01"

    # Density filter
    dense_results = provider.search(min_density=35.0)
    assert len(dense_results) >= 1
    for r in dense_results:
        assert r["point_density"] >= 35.0

def test_gliht_pdal_reader():
    """Verify PDAL reader pipeline stage generation."""
    provider = GLiHTProvider()
    urls = ["https://glihtdata.gsfc.nasa.gov/data/pub/Sierra_2022/las/Sierra_20220718_FL01_las.laz"]
    buffered_poly = box(759000, 4313000, 759500, 4313500)

    stages = provider.get_pdal_reader(urls, buffered_poly, poly_crs="EPSG:32610")
    assert len(stages) == 2
    assert stages[0]["type"] == "readers.las"
    assert stages[0]["filename"] == urls[0]
    assert stages[0]["spatialreference"] == "EPSG:32610"
    assert stages[1]["type"] == "filters.crop"
    assert "bounds" in stages[1]
