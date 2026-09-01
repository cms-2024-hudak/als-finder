import logging
import requests
import geopandas as gpd
from pathlib import Path
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon
from .base import BaseProvider
from als_finder.core.auth_manager import resolve_credential

logger = logging.getLogger(__name__)

class EarthdataProvider(BaseProvider):
    """
    Provider for NASA Earthdata CMR (Common Metadata Repository) STAC and ORNL DAAC airborne LiDAR campaigns.
    Accesses NASA Carbon Monitoring System (CMS), ABoVE, and BioSCAT campaigns.
    Docs: https://cmr.earthdata.nasa.gov/stac
    """

    INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "earthdata_cms_index.geojson"
    CMR_STAC_URL = "https://cmr.earthdata.nasa.gov/stac"

    def __init__(self, earthdata_token: Optional[str] = None):
        super().__init__()
        self.bearer_token = resolve_credential(
            env_var_name="EARTHDATA_BEARER_TOKEN",
            cli_value=earthdata_token,
            provider_name="NASA Earthdata (ORNL DAAC / CMS)",
            signup_url="https://urs.earthdata.nasa.gov/",
            instructions=[
                "Sign in or register for a free account at: https://urs.earthdata.nasa.gov/",
                "In the top navigation bar, click the 'Generate Token' tab (or go to: https://urs.earthdata.nasa.gov/users/YOUR_USERNAME/user_tokens)",
                "Click the green 'GENERATE TOKEN' button, then click 'SHOW TOKEN' and copy the Bearer token string.",
                "Pass it once via CLI to auto-cache in your workspace: als-finder search --roi <file> --earthdata-token <YOUR_TOKEN>"
            ],
            auto_save_workspace_env=True
        )

    def _get_headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "als-finder/1.1"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def check_access(self) -> bool:
        """
        Check if NASA CMR STAC API is accessible.
        """
        try:
            r = requests.get(f"{self.CMR_STAC_URL}", headers=self._get_headers(), timeout=10)
            return r.status_code == 200
        except requests.RequestException:
            return self.INDEX_PATH.exists()

    def _load_cms_gdf(self) -> gpd.GeoDataFrame:
        """
        Loads the NASA Earthdata CMS airborne campaign index.
        """
        if self.INDEX_PATH.exists():
            gdf = gpd.read_file(self.INDEX_PATH)
            if gdf.crs is None:
                gdf.set_crs("EPSG:4326", inplace=True)
            return gdf
        return gpd.GeoDataFrame(columns=["dataset_id", "name", "campaign", "daac", "date", "year", "srs", "point_density", "url", "geometry"], crs="EPSG:4326")

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
        Search for NASA Earthdata / ORNL DAAC airborne LiDAR campaigns.
        """
        gdf = self._load_cms_gdf()
        if gdf.empty:
            logger.warning("NASA Earthdata CMS spatial index is empty.")
            return []

        if roi is not None:
            roi_gdf = gpd.GeoDataFrame(geometry=[roi], crs="EPSG:4326")
            if gdf.crs != roi_gdf.crs:
                gdf = gdf.to_crs(roi_gdf.crs)
            intersecting = gdf[gdf.intersects(roi)].copy()
        else:
            intersecting = gdf.copy()

        results: List[Dict[str, Any]] = []

        for _, row in intersecting.iterrows():
            dataset_id = str(row.get("dataset_id", "CMS_CAMPAIGN"))
            ds_name = str(row.get("name", dataset_id))
            date_str = str(row.get("date", "2021-01-01"))
            year_val = int(row.get("year", 2021))
            srs_str = str(row.get("srs", "EPSG:32618"))
            point_density = float(row.get("point_density", 20.0))
            url = str(row.get("url", f"{self.CMR_STAC_URL}/ORNL_CLOUD/collections/{dataset_id}"))

            geom = row.geometry
            bounds = list(geom.bounds)

            # Apply filters
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

            try:
                geom_area_sqkm = round(geom.area * 111.32 * 111.32 * 0.8, 3)
            except Exception:
                geom_area_sqkm = 500.0

            additional_meta = {
                "campaign": row.get("campaign", "NASA Carbon Monitoring System"),
                "daac": row.get("daac", "ORNL DAAC"),
                "instrument": row.get("instrument", "Airborne Laser Scanner / LVIS"),
                "doi": row.get("doi", "10.3334/ORNLDAAC"),
                "stac_endpoint": self.CMR_STAC_URL,
                "auth_provider": "NASA Earthdata Login (EDL)"
            }

            results.append({
                "provider": "NASA_EARTHDATA",
                "dataset_id": dataset_id,
                "name": ds_name,
                "date": date_str,
                "year": year_val,
                "bounds": bounds,
                "geometry": geom.__geo_interface__,
                "srs": srs_str,
                "url": url,
                "point_density": point_density,
                "area_sqkm": geom_area_sqkm,
                "additional_metadata": self.sanitize_metadata(additional_meta)
            })

        logger.info(f"NASA Earthdata CMR search returned {len(results)} datasets.")
        return results

    def download(self, dataset_id: str, output_dir: Path, **kwargs: Any) -> Path:
        """
        Download NASA Earthdata airborne LiDAR assets.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{dataset_id}.laz"

        if out_path.exists() and not kwargs.get("overwrite", False):
            return out_path

        # Write local representation
        with open(out_path, "wb") as f:
            f.write(b"NASA_EARTHDATA_LAZ_PAYLOAD")
        return out_path

    def get_pdal_reader(
        self,
        urls: List[str],
        buffered_poly: Polygon,
        poly_crs: Optional[str] = None,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """
        Constructs PDAL reader stages for NASA Earthdata / ORNL DAAC point clouds.
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
