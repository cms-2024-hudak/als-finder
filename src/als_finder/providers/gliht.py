import logging
import json
import requests
import geopandas as gpd
from pathlib import Path
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon, shape
from .base import BaseProvider

logger = logging.getLogger(__name__)

class GLiHTProvider(BaseProvider):
    """
    Provider for NASA G-LiHT (Goddard LiDAR, Hyperspectral & Thermal Imager) point clouds.
    Searches flight swath boundaries and directly interfaces with GSFC data endpoints.
    """

    INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "gliht_index.geojson"
    REMOTE_INDEX_URL = "https://gliht.gsfc.nasa.gov/api/v1/footprints.geojson"
    CACHE_DIR = Path.home() / ".cache" / "als_finder"
    CACHE_FILE = CACHE_DIR / "gliht_footprints.geojson"

    def __init__(self):
        super().__init__()

    def check_access(self) -> bool:
        """
        Check if G-LiHT provider index is available.
        """
        return self.INDEX_PATH.exists() or self.CACHE_FILE.exists()

    def _load_index_gdf(self) -> gpd.GeoDataFrame:
        """
        Loads the G-LiHT flight footprint index into a GeoDataFrame.
        Tries local cached remote index first, falling back to built-in bundled index.
        """
        if self.CACHE_FILE.exists() and self.CACHE_FILE.stat().st_size > 1000:
            try:
                gdf = gpd.read_file(self.CACHE_FILE)
                if not gdf.empty:
                    if gdf.crs is None:
                        gdf.set_crs("EPSG:4326", inplace=True)
                    return gdf
            except Exception as e:
                logger.warning(f"Failed to read cached G-LiHT index: {e}. Falling back to bundled index.")

        if self.INDEX_PATH.exists():
            gdf = gpd.read_file(self.INDEX_PATH)
            if gdf.crs is None:
                gdf.set_crs("EPSG:4326", inplace=True)
            return gdf

        # Empty fallback GeoDataFrame
        return gpd.GeoDataFrame(
            columns=["dataset_id", "name", "campaign", "flight_line", "date", "year", "srs", "point_density", "url", "geometry"],
            crs="EPSG:4326"
        )

    def search(
        self,
        roi: Optional[Polygon] = None,
        name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_density: Optional[float] = None,
        max_density: Optional[float] = None,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """
        Search for NASA G-LiHT LiDAR datasets intersecting the ROI and matching filter criteria.
        """
        gdf = self._load_index_gdf()
        if gdf.empty:
            logger.warning("NASA G-LiHT spatial index is empty.")
            return []

        # Spatial filter
        if roi is not None:
            roi_gdf = gpd.GeoDataFrame(geometry=[roi], crs="EPSG:4326")
            if gdf.crs != roi_gdf.crs:
                gdf = gdf.to_crs(roi_gdf.crs)
            intersecting = gdf[gdf.intersects(roi)].copy()
        else:
            intersecting = gdf.copy()

        results: List[Dict[str, Any]] = []

        for _, row in intersecting.iterrows():
            geom = row.geometry
            props = row.to_dict()
            props.pop("geometry", None)

            dataset_id = str(props.get("dataset_id", "GLIHT_UNKNOWN"))
            ds_name = str(props.get("name", dataset_id))
            date_str = str(props.get("date", "2020-01-01"))
            year_val = int(props.get("year", date_str.split("-")[0] if "-" in date_str else 2020))
            srs_str = str(props.get("srs", "EPSG:32610"))
            point_density = float(props.get("point_density", 30.0))
            url = str(props.get("url", f"https://glihtdata.gsfc.nasa.gov/data/pub/las/{dataset_id}.laz"))

            # Filtering checks
            if name and name.lower() not in ds_name.lower() and name.lower() not in dataset_id.lower():
                continue
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            if min_density is not None and point_density < min_density:
                continue
            if max_density is not None and point_density > max_density:
                continue

            bounds = list(geom.bounds)  # [minx, miny, maxx, maxy]

            # Calculate approximate area in sq km
            try:
                geom_area_sqkm = round(geom.area * 111.32 * 111.32 * 0.8, 3)
            except Exception:
                geom_area_sqkm = 1.0

            additional_meta = {
                "campaign": props.get("campaign", "NASA Airborne Science"),
                "flight_line": props.get("flight_line", "FL01"),
                "instrument": props.get("instrument", "Riegl VQ-480 Airborne Laser Scanner"),
                "sensor_type": props.get("sensor_type", "Discrete Return & Waveform LiDAR"),
                "ancillary_sensors": props.get("ancillary_sensors", "Hyperspectral (VNIR), Thermal IR, RGB Orthomosaic"),
                "altitude_m_agl": props.get("altitude_m_agl", 335),
                "landing_page": props.get("landing_page", "https://gliht.gsfc.nasa.gov/"),
                "provider_type": "NASA_Airborne"
            }

            estimated_pts = int(point_density * geom_area_sqkm * 1_000_000)
            estimated_bytes = estimated_pts * 8

            results.append({
                "provider": "NASA_GLIHT",
                "dataset_id": dataset_id,
                "name": ds_name,
                "date": date_str,
                "year": year_val,
                "bounds": bounds,
                "geometry": geom.__geo_interface__,
                "srs": srs_str,
                "url": url,
                "point_density": point_density,
                "point_count": estimated_pts,
                "size": estimated_bytes,
                "area_sqkm": geom_area_sqkm,
                "additional_metadata": self.sanitize_metadata(additional_meta)
            })

        logger.info(f"NASA G-LiHT search returned {len(results)} datasets.")
        return results

    def download(self, dataset_id: str, output_dir: Path, **kwargs: Any) -> Path:
        """
        Download a NASA G-LiHT .laz file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        url = kwargs.get("url")

        if not url:
            gdf = self._load_index_gdf()
            match = gdf[gdf["dataset_id"] == dataset_id]
            if not match.empty:
                url = match.iloc[0]["url"]
            else:
                url = f"https://glihtdata.gsfc.nasa.gov/data/pub/las/{dataset_id}.laz"

        out_path = output_dir / f"{dataset_id}.laz"
        if out_path.exists() and not kwargs.get("overwrite", False):
            logger.info(f"Using existing G-LiHT file: {out_path}")
            return out_path

        logger.info(f"Streaming NASA G-LiHT swath from {url} -> {out_path}...")
        try:
            with requests.get(url, stream=True, timeout=60, headers={"User-Agent": "als-finder/1.1"}) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            logger.info(f"Successfully downloaded {out_path}")
            return out_path
        except requests.RequestException as e:
            logger.error(f"Failed to download G-LiHT dataset {dataset_id}: {e}")
            raise

    def get_pdal_reader(
        self,
        urls: List[str],
        buffered_poly: Polygon,
        poly_crs: Optional[str] = None,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """
        Constructs PDAL reader stages for G-LiHT swath data.
        Uses readers.las with spatial bounding crop for out-of-core sub-tiling.
        """
        minx, miny, maxx, maxy = buffered_poly.bounds
        bounds_str = f"([{minx}, {maxx}], [{miny}, {maxy}])"

        stages: List[Dict[str, Any]] = []
        for url in urls:
            stages.append({
                "type": "readers.las",
                "filename": url,
                "spatialreference": poly_crs or "EPSG:4326"
            })

        if len(stages) > 1:
            stages.append({"type": "filters.merge"})

        stages.append({
            "type": "filters.crop",
            "bounds": bounds_str
        })

        return stages
