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
