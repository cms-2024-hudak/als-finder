from pathlib import Path
import pytest
from shapely.geometry import Polygon
from als_finder.core.input_manager import load_roi, ROIError, validate_roi
import geopandas as gpd

@pytest.fixture
def roi_file(tmp_path):
    """Creates a temporary GeoJSON file."""
    p = tmp_path / "test_roi.geojson"
    # Create a simple box in a GeoDataFrame
    poly = Polygon([[-120, 38], [-119, 38], [-119, 39], [-120, 39], [-120, 38]])
    gdf = gpd.GeoDataFrame({'geometry': [poly]}, crs="EPSG:4326")
    gdf.to_file(p, driver="GeoJSON")
    return p

def test_load_roi_from_bbox_list():
    bbox = [-120.25, 38.85, -119.85, 39.25]
    geom = load_roi(bbox)
    assert isinstance(geom, Polygon)
    assert validate_roi(geom)
    minx, miny, maxx, maxy = geom.bounds
    assert minx == -120.25

def test_load_roi_from_bbox_string():
    bbox_str = "-120.0, 38.0, -119.0, 39.0"
    geom = load_roi(bbox_str)
    assert isinstance(geom, Polygon)
    assert validate_roi(geom)

def test_load_roi_from_file(roi_file):
    geom = load_roi(roi_file)
    assert isinstance(geom, Polygon)
    assert validate_roi(geom)

def test_invalid_roi_bbox():
    # minx > maxx
    with pytest.raises(ROIError):
        load_roi([0, 0, -1, 1])

def test_missing_file():
    with pytest.raises(ROIError):
        load_roi("non_existent_file.geojson")
