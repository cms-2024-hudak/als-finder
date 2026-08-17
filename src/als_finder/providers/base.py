from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon
from pathlib import Path

class BaseProvider(ABC):
    """Abstract base class for LiDAR data providers."""

    @abstractmethod
    def search(self, roi: Optional[Polygon] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for datasets within the ROI or across global footprints using mathematical API intercepts.

        Args:
            roi (Optional[Polygon]): Region of Interest boundary mapping. If None, queries mathematically skip initial geometric intercept arrays bounding universally.
            **kwargs: Additional search parameters mapped natively into local provider filter mechanisms (e.g., `name`, `start_date`, `end_date`, `min_density`, `max_density`).

        Returns:
            List[Dict]: A list of metadata dictionaries uniformly mapping exactly found datasets dynamically intercepted natively.
        """
        pass

    @abstractmethod
    def download(self, dataset_id: str, output_dir: Path, **kwargs) -> Path:
        """
        Download a specific dataset.

        Args:
            dataset_id (str): ID of the dataset to download.
            output_dir (Path): Local directory to save files.
            **kwargs: Additional download parameters.

        Returns:
            Path: Path to the downloaded file or directory.
        """
        pass

    @abstractmethod
    def check_access(self) -> bool:
        """
        Check if the provider is accessible and authentication is valid.
        
        Returns:
            bool: True if accessible, False otherwise.
        """
        pass

    @abstractmethod
    def get_pdal_reader(
        self,
        urls: List[str],
        buffered_poly: Polygon,
        poly_crs: Optional[str] = None,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """
        Constructs the provider-specific PDAL reader pipeline stages.
        This allows each provider to handle its own spatial subsetting logic natively.
        
        Args:
            urls (List[str]): List of remote URLs intersecting the processing tile.
            buffered_poly (Polygon): The spatial processing bounds.
            poly_crs (Optional[str]): Coordinate reference system of buffered_poly.
            **kwargs: Additional provider-specific parameters.
            
        Returns:
            List[Dict]: A list of PDAL stage dictionaries (readers + potential merges).
        """
        pass

    @staticmethod
    def sanitize_metadata(raw_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Ensures all keys and values in an additional_metadata dictionary are JSON-serializable primitives.
        Converts non-serializable objects (such as Shapely geometries, Path objects, Datetime) to strings.
        
        Args:
            raw_dict (Optional[Dict[str, Any]]): Raw dictionary from provider API.
            
        Returns:
            Dict[str, Any]: Clean, JSON-safe metadata dictionary.
        """
        if not raw_dict or not isinstance(raw_dict, dict):
            return {}
        clean = {}
        for k, v in raw_dict.items():
            if k in ("geometry", "buffered_geometry", "buffered_poly", "core_poly"):
                continue
            if isinstance(v, (str, int, float, bool, type(None))):
                clean[str(k)] = v
            elif isinstance(v, (list, tuple)):
                clean[str(k)] = [str(item) if not isinstance(item, (int, float, bool, type(None))) else item for item in v]
            elif isinstance(v, dict):
                clean[str(k)] = BaseProvider.sanitize_metadata(v)
            else:
                clean[str(k)] = str(v)
        return clean


