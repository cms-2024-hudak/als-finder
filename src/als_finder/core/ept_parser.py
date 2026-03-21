import requests
import pyproj
from typing import List, Tuple
from shapely.geometry import box, Polygon
from shapely.ops import transform
import logging

logger = logging.getLogger(__name__)

class EPTParser:
    def __init__(self, ept_url: str):
        self.ept_url = ept_url.rstrip('/')
        if self.ept_url.endswith('ept.json'):
            self.base_url = self.ept_url.rsplit('/', 1)[0]
        else:
            self.base_url = self.ept_url
            self.ept_url = f"{self.base_url}/ept.json"
            
        r = requests.get(self.ept_url)
        r.raise_for_status()
        self.metadata = r.json()
        self.root_bounds = self.metadata['bounds']
        self.intersecting_urls = []
        
        self.epsg = self.metadata.get('srs', {}).get('horizontal', '3857')

    def get_node_bounds(self, node_id: str):
        d, x, y, z = map(int, node_id.split('-'))
        minX, minY, minZ, maxX, maxY, maxZ = self.root_bounds
        
        W = (maxX - minX) / (2 ** d)
        H = (maxY - minY) / (2 ** d)
        
        nx_min = minX + (x * W)
        nx_max = minX + ((x + 1) * W)
        ny_min = minY + (y * H)
        ny_max = minY + ((y + 1) * H)
        return box(nx_min, ny_min, nx_max, ny_max)
        
    def find_intersecting_laz(self, roi_wgs84: Polygon) -> List[Tuple[str, int]]:
        project = pyproj.Transformer.from_crs(
            pyproj.CRS('EPSG:4326'), 
            pyproj.CRS(f'EPSG:{self.epsg}'), 
            always_xy=True
        ).transform
        roi_native = transform(project, roi_wgs84)
        
        self.intersecting_urls = []
        self._traverse_hierarchy("0-0-0-0", roi_native)
        return self.intersecting_urls
        
    def _traverse_hierarchy(self, node_id: str, roi: Polygon):
        h_url = f"{self.base_url}/ept-hierarchy/{node_id}.json"
        try:
            r = requests.get(h_url, timeout=10)
            if r.status_code != 200:
                logger.debug(f"Missing logical hierarchy fallback: {h_url} - {r.status_code}")
                return
        except Exception as e:
            logger.warning(f"Request failed structurally for {h_url}: {e}")
            return
            
        h_data = r.json()
        for child_id, count in h_data.items():
            child_box = self.get_node_bounds(child_id)
            if not roi.intersects(child_box):
                continue
                
            if count == -1:
                self._traverse_hierarchy(child_id, roi)
            elif count > 0:
                laz_url = f"{self.base_url}/ept-data/{child_id}.laz"
                self.intersecting_urls.append((laz_url, count))
