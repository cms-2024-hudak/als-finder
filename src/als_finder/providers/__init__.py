import logging
from typing import Dict, Type, List, Optional
from .base import BaseProvider
from .usgs import USGSProvider
from .opentopography import OpenTopographyProvider
from .noaa import NOAAProvider
from .gliht import GLiHTProvider
from .neon import NEONProvider
from .earthdata import EarthdataProvider

logger = logging.getLogger(__name__)

# Registry mappings
PROVIDER_REGISTRY: Dict[str, Type[BaseProvider]] = {}
PROVIDER_ALIASES: Dict[str, str] = {}

def register_provider(*names: str):
    """
    Decorator to register a provider class with one or more lookup keys / aliases.
    """
    def decorator(cls: Type[BaseProvider]):
        if not names:
            canonical_name = cls.__name__.replace("Provider", "").upper()
            all_names = [canonical_name]
        else:
            canonical_name = names[0].upper()
            all_names = names

        PROVIDER_REGISTRY[canonical_name] = cls
        for alias in all_names:
            PROVIDER_ALIASES[alias.strip().upper()] = canonical_name
        return cls
    return decorator

# Explicitly register standard providers
register_provider("USGS_EPT", "USGS", "EPT", "3DEP")(USGSProvider)
register_provider("OPENTOPOGRAPHY", "OT", "OPEN_TOPO", "OPENTOPO")(OpenTopographyProvider)
register_provider("NOAA_STAC", "NOAA", "DIGITAL_COAST")(NOAAProvider)
register_provider("NASA_GLIHT", "GLIHT", "G-LIHT", "NASA")(GLiHTProvider)
register_provider("NEON_AOP", "NEON", "AOP")(NEONProvider)
register_provider("NASA_EARTHDATA", "EARTHDATA", "CMR", "ORNL_DAAC", "CMS")(EarthdataProvider)

def get_provider(name: str) -> BaseProvider:
    """
    Instantiate a provider by canonical name or alias.
    """
    key = str(name).strip().upper()
    canonical = PROVIDER_ALIASES.get(key, key)
    if canonical in PROVIDER_REGISTRY:
        return PROVIDER_REGISTRY[canonical]()
    raise ValueError(f"Unknown provider: '{name}'. Available: {list_available_providers()}")

def get_active_providers(provider_names: Optional[List[str]] = None) -> List[BaseProvider]:
    """
    Return a list of initialized provider instances matching requested names/aliases.
    If provider_names is None or empty, returns all registered standard providers.
    """
    if not provider_names:
        return [cls() for cls in PROVIDER_REGISTRY.values()]

    seen = set()
    active: List[BaseProvider] = []
    for p in provider_names:
        key = str(p).strip().upper()
        canonical = PROVIDER_ALIASES.get(key, key)
        if canonical in PROVIDER_REGISTRY and canonical not in seen:
            seen.add(canonical)
            active.append(PROVIDER_REGISTRY[canonical]())
        elif canonical not in PROVIDER_REGISTRY:
            logger.warning(f"Unrecognized provider requested: '{p}'. Skipping.")
    return active

def list_available_providers() -> List[str]:
    """
    Return a list of all registered provider canonical names.
    """
    return list(PROVIDER_REGISTRY.keys())

__all__ = [
    "BaseProvider",
    "USGSProvider",
    "OpenTopographyProvider",
    "NOAAProvider",
    "GLiHTProvider",
    "NEONProvider",
    "EarthdataProvider",
    "register_provider",
    "get_provider",
    "get_active_providers",
    "list_available_providers",
    "PROVIDER_REGISTRY"
]
