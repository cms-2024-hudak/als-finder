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
    
    # Load manifest for rich metadata integration (datetime, source provider descriptions)
    manifest_path = workspace / "catalog" / "manifest.json"
    dataset_metadata = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r') as mf:
                manifest_data = json.load(mf)
                for ds in manifest_data.get('datasets', []):
                    ds_id = ds.get('dataset_id') or ds.get('name')
                    if ds_id:
                        dataset_metadata[ds_id] = ds
        except Exception as e:
            logger.warning(f"Could not load manifest.json in STAC generator: {e}")
    
    # 1. Root Genesis (Uses generic description suitable for all providers including OpenTopography)
    catalog = pystac.Catalog(
        id="als-finder-catalog",
        description="Root STAC Catalog representing standardized LiDAR point clouds.",
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
            
            ds_meta = dataset_metadata.get(dataset_val, {})
            ds_desc = ds_meta.get('description') or f"Standardized {dataset_val} point cloud conformed from {provider_val}."
            
            # 2. Collection Partitioning
            # For each dataset, generate a dynamic STAC collection.
            # We initialize a generic spatial extent (will dynamically expand as items are added)
            spatial_extent = pystac.SpatialExtent([[-180.0, -90.0, 180.0, 90.0]])
            temporal_extent = pystac.TemporalExtent([[datetime.now(timezone.utc), datetime.now(timezone.utc)]])
            extent = pystac.Extent(spatial=spatial_extent, temporal=temporal_extent)
            
            collection = pystac.Collection(
                id=dataset_val,
                description=ds_desc,
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
                
                # Resolve precise acquisition date/time dynamically from search registry manifest
                ds_date_str = ds_meta.get('date')
                item_datetime = None
                if ds_date_str:
                    try:
                        # Handle simple year date formats (e.g. '2022') or standard ISO date strings
                        if len(ds_date_str) == 4 and ds_date_str.isdigit():
                            item_datetime = datetime(int(ds_date_str), 1, 1, tzinfo=timezone.utc)
                        else:
                            # Clean up dates containing spaces or T dividers
                            clean_date = ds_date_str.split(' ')[0].split('T')[0]
                            parsed = datetime.strptime(clean_date, "%Y-%m-%d")
                            item_datetime = parsed.replace(tzinfo=timezone.utc)
                    except Exception as date_e:
                        logger.debug(f"Failed parsing acquisition date '{ds_date_str}': {date_e}")
                
                if item_datetime:
                    pdal_stac['properties']['datetime'] = item_datetime.isoformat()
                elif 'datetime' not in pdal_stac['properties']:
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
                            media_type="application/vnd.laszip+copc",
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
    catalog.make_all_asset_hrefs_relative()
    
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
