import json
import pytest
from shapely.geometry import box
from als_finder.providers import (
    get_provider,
    EarthdataProvider
)

def test_earthdata_provider_registration():
    """Verify Earthdata provider registration and aliases."""
    p1 = get_provider("earthdata")
    p2 = get_provider("NASA_EARTHDATA")
    p3 = get_provider("cmr")
    p4 = get_provider("ornl_daac")
    assert isinstance(p1, EarthdataProvider)
    assert isinstance(p2, EarthdataProvider)
    assert isinstance(p3, EarthdataProvider)
    assert isinstance(p4, EarthdataProvider)

def test_earthdata_spatial_search():
    """Verify NASA Earthdata CMS spatial search."""
    provider = EarthdataProvider()
    # ROI covering Maryland Mid-Atlantic CMS campaign
    roi = box(-77.00, 39.00, -76.80, 39.20)
    results = provider.search(roi=roi)

    assert len(results) >= 1
    md_res = results[0]
    assert md_res["provider"] == "NASA_EARTHDATA"
    assert "CMS_MD" in md_res["dataset_id"]
    assert md_res["srs"] == "EPSG:32618"
    assert "cmr.earthdata.nasa.gov" in md_res["url"]
    assert md_res["additional_metadata"]["daac"] == "ORNL DAAC"

    # Verify JSON serialization
    json_str = json.dumps(md_res)
    assert len(json_str) > 50

def test_earthdata_pdal_reader():
    """Verify PDAL reader pipeline construction."""
    provider = EarthdataProvider()
    urls = ["https://cmr.earthdata.nasa.gov/stac/ORNL_CLOUD/collections/CMS_MD_2021/item.laz"]
    buffered_poly = box(320000, 4320000, 3210000, 4321000)

    stages = provider.get_pdal_reader(urls, buffered_poly, poly_crs="EPSG:32618")
    assert len(stages) == 2
    assert stages[0]["type"] == "readers.las"
    assert stages[1]["type"] == "filters.crop"
