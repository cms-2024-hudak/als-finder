"""
LiDAR Data Finder Package
"""
import importlib.metadata
import os
import sys
from pathlib import Path

# Automatically ensure PROJ_DATA is set if running within a conda prefix
prefix_proj = Path(sys.prefix) / "share" / "proj"
if prefix_proj.exists():
    os.environ.setdefault("PROJ_DATA", str(prefix_proj))
    os.environ.setdefault("PROJ_LIB", str(prefix_proj))

try:
    __version__ = importlib.metadata.version("als-finder")
except importlib.metadata.PackageNotFoundError:
    __version__ = "1.1.1-dev"

