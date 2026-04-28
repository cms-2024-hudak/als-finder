import logging
import json
import subprocess
from pathlib import Path
import geopandas as gpd
from shapely.geometry import shape

logger = logging.getLogger(__name__)

def generate_local_catalog(workspace: Path, target_crs: str) -> bool:
    """
    Scans the standardized LiDAR payloads and generates a tight boundary catalog 
    natively using PDAL hexbins, optimized for COPC streaming.
    """
    standardized_dir = workspace / "data" / "standardized"
    
    if not standardized_dir.exists():
        logger.error(f"Cannot generate local catalog. Standardized array does not exist natively: {standardized_dir}")
        return False
        
    catalog_dir = workspace / "catalog"
    manifest_path = catalog_dir / "manifest.json"
    out_gpkg = catalog_dir / "standardized_catalog.gpkg"
    
    if not manifest_path.exists():
        logger.warning(f"No manifest.json found in {catalog_dir}. Cannot merge metadata natively.")
        return False
        
    with open(manifest_path, 'r') as f:
        manifest_data = json.load(f)
        
    datasets_meta = {}
    for item in manifest_data.get('datasets', []):
        datasets_meta[item['name']] = item
        
    laz_files = list(standardized_dir.rglob("*.copc.laz"))
    
    if not laz_files:
        logger.warning(f"No COPC files structurally located inside {standardized_dir}.")
        return False
        
    logger.info(f"Extracting tight COPC hexbin footprints dynamically across {len(laz_files)} nodes...")
    
    records = []
    
    for laz_file in laz_files:
        dataset_name = laz_file.parent.name.replace('dataset=', '')
        
        try:
            # Execute simple, stable pdal info --boundary directly
            # This completely avoids all JSON pipeline parsing, STDIN pipe deadlocks,
            # and octree thrashing by utilizing the compiled C++ binary natively.
            res = subprocess.run(
                ['pdal', 'info', '--boundary', str(laz_file.absolute())], 
                capture_output=True, 
                text=True,
                check=True
            )
            
            meta = json.loads(res.stdout)
            boundary_json = meta.get('boundary', {}).get('boundary_json')
            
            if not boundary_json:
                raise ValueError("No boundary_json generated structurally by pdal info.")
                
            geom = shape(boundary_json)
            
            original_meta = datasets_meta.get(dataset_name, {})
            
            record = {
                'id': laz_file.stem,
                'dataset': dataset_name,
                'provider': original_meta.get('provider', 'UNKNOWN'),
                'date': original_meta.get('date', ''),
                'point_density': original_meta.get('point_density', 0.0),
                'geometry': geom
            }
            records.append(record)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"PDAL pipeline failed for {laz_file.name}: {e.stderr.decode('utf-8')}")
        except Exception as e:
            logger.error(f"Failed to generate tight footprint natively for {laz_file.name}: {e}")
            
    if not records:
        logger.error("No footprint matrices were successfully extracted natively.")
        return False
        
    try:
        # Default fallback to Web Mercator if crs not passed properly
        if not target_crs:
            target_crs = "EPSG:3857"
            
        gdf = gpd.GeoDataFrame(records, crs=target_crs)
        # Natively save without reprojection to maintain pipeline geometry
        gdf.to_file(str(out_gpkg.absolute()), driver="GPKG")
        logger.info(f"[SUCCESS] Native Standardized Catalog mapped tightly in {target_crs}: {out_gpkg.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to compile GeoDataFrame catalog natively: {e}")
        return False
