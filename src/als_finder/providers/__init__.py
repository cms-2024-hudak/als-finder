from .base import BaseProvider
from .opentopography import OpenTopographyProvider
from .usgs import USGSProvider
from .noaa import NOAAProvider

__all__ = ['BaseProvider', 'OpenTopographyProvider', 'USGSProvider', 'NOAAProvider', 'get_provider']

def get_provider(name: str) -> BaseProvider:
    if name == "USGS_EPT":
        return USGSProvider()
    elif name == "OpenTopography":
        return OpenTopographyProvider()
    elif name == "NOAA_STAC":
        return NOAAProvider()
    else:
        raise ValueError(f"Unknown provider: {name}")
