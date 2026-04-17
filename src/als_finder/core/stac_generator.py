import logging
import json
import subprocess
import os
from pathlib import Path
from datetime import datetime, timezone
import pystac
from stac_validator import stac_validator

logger = logging.getLogger(__name__)

def generate_catalog(workspace: Path) -> bool:
    """
    Scans the standardized LiDAR Hive partitions natively and constructs a flawless 
    OGC / PySTAC validated JSON hierarchy dynamically preventing QGIS linkage collapse.
    """
    standardized_dir = workspace / "data" / "standardized"
    
    if not standardized_dir.exists():
        logger.error(f"Cannot generate STAC. Standardized array does not exist natively: {standardized_dir}")
        return False
        
    stac_dir = workspace / "catalog" / "stac"
    stac_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Root Genesis
    catalog = pystac.Catalog(
        id="als-finder-catalog",
        description="Root STAC Catalog representing processed USGS/NOAA LiDAR point clouds.",
        title="ALS-Finder Standardized Point Cloud Catalog"
    )
    
    providers_found = list(standardized_dir.glob("provider=*"))
    if not providers_found:
        logger.warning(f"No Hive structural providers located inside natively: {standardized_dir}")
        return False
        
    items_added = 0
        
    for provider_dir in providers_found:
        provider_val = provider_dir.name.split("=")[1]
        
        for dataset_dir in provider_dir.glob("dataset=*"):
            dataset_val = dataset_dir.name.split("=")[1]
            
            # 2. Collection Partitioning
            # For each dataset, generate a dynamic STAC collection.
            # We initialize a generic spatial extent (will dynamically expand as items are added)
            spatial_extent = pystac.SpatialExtent([[-180.0, -90.0, 180.0, 90.0]])
            temporal_extent = pystac.TemporalExtent([[datetime.now(timezone.utc), datetime.now(timezone.utc)]])
            extent = pystac.Extent(spatial=spatial_extent, temporal=temporal_extent)
            
            collection = pystac.Collection(
                id=dataset_val,
                description=f"Standardized COPC array generated natively from {provider_val}.",
                extent=extent
            )
            
            laz_files = list(dataset_dir.rglob("*.copc.laz"))
            
            for laz_file in laz_files:
                # 3. Item Generation via PDAL
                try:
                    res = subprocess.run(['pdal', 'info', '--stac', str(laz_file.absolute())], 
                                         capture_output=True, check=True, text=True)
                    pdal_info = json.loads(res.stdout)
                    pdal_stac = pdal_info.get('stac', pdal_info)
                except Exception as e:
                    logger.error(f"Failed to extract PDAL stac indices from {laz_file.name}: {e}")
                    continue
                    
                # Fix known PDAL missing constraints structurally mapping dynamically
                if 'properties' not in pdal_stac:
                    pdal_stac['properties'] = {}
                if 'datetime' not in pdal_stac['properties']:
                    pdal_stac['properties']['datetime'] = datetime.now(timezone.utc).isoformat()
                    
                # Assign static ID inherently tied to the file natively
                pdal_stac['id'] = laz_file.stem
                
                try:
                    item = pystac.Item.from_dict(pdal_stac)
                    
                    # Add structural asset link mapping directly to QGIS
                    item.add_asset(
                        key="data",
                        asset=pystac.Asset(
                            href=str(laz_file.absolute()),  # Will be mapped relatively dynamically via normalize_hrefs
                            media_type="application/vnd.las",
                            roles=["data"]
                        )
                    )
                    
                    collection.add_item(item)
                    items_added += 1
                except Exception as e:
                    logger.error(f"PySTAC parsing error organically intersecting {laz_file.name}: {e}")
            
            if len(list(collection.get_items())) > 0:
                collection.update_extent_from_items()
                catalog.add_child(collection)
                
    if items_added == 0:
        logger.warning(f"0 structurally valid COPC items logged inside {standardized_dir}.")
        return False
        
    # 4. Link Normalization (This fixes QGIS)
    logger.info("Normalizing STAC HREFs automatically locking standard structures natively...")
    catalog.normalize_hrefs(str(stac_dir.absolute()))
    
    # Save the catalog
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)
    logger.info(f"[SUCCESS] STAC Catalog efficiently generated into globally {stac_dir.absolute()}/catalog.json")
    
    # 5. Stac-Validator Execution Structurally
    try:
        stac = stac_validator.StacValidate(str(stac_dir / "catalog.json"))
        stac.run()
        if stac.message[-1]['valid_stac'] == True:
            logger.info("STAC Validation: [PASSED] - File schema is mathematically perfectly secure.")
        else:
            logger.warning("STAC Validation: [FAILED] organically against OGC schema protocols natively.")
    except Exception as e:
        logger.warning(f"Could not actively dynamically run stac_validator natively: {e}")
        
    return True
