import pytest
from pathlib import Path

@pytest.fixture
def sample_roi():
    """Returns a sample GeoJSON dictionary for testing."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-120.25, 38.85],
                            [-119.85, 38.85],
                            [-119.85, 39.25],
                            [-120.25, 39.25],
                            [-120.25, 38.85]
                        ]
                    ]
                }
            }
        ]
    }
