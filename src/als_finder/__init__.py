"""
LiDAR Data Finder Package
"""
import importlib.metadata

try:
    __version__ = importlib.metadata.version("als-finder")
except importlib.metadata.PackageNotFoundError:
    __version__ = "1.1.1-dev"
