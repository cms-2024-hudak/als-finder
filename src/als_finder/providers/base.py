from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon
from pathlib import Path

class BaseProvider(ABC):
    """Abstract base class for LiDAR data providers."""

    @abstractmethod
    def search(self, roi: Polygon, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for datasets within the ROI.

        Args:
            roi (Polygon): Region of Interest.
            **kwargs: Additional search parameters (dates, density, etc.)

        Returns:
            List[Dict]: A list of metadata dictionaries for found datasets.
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
