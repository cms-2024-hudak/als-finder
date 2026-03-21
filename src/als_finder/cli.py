import click
import logging
import json
import os
import shutil
from datetime import datetime
import time
from dotenv import load_dotenv
from als_finder.core.input_manager import load_roi, ROIError
from als_finder.providers import OpenTopographyProvider, USGSProvider, NOAAProvider

from als_finder.providers import OpenTopographyProvider, USGSProvider, NOAAProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.group()
def cli():
    """LiDAR Data Finder CLI"""
    pass

@cli.command()
@click.option('--roi', required=True, help='Path to ROI file (GeoJSON/Shapefile) or BBox string')
@click.option('--start-date', help='Start date (YYYY-MM-DD)')
@click.option('--end-date', help='End date (YYYY-MM-DD)')
@click.option('--workspace', help='Path to project workspace directory')
@click.option('--quiet', is_flag=True, help='Suppress standard terminal output')
@click.option('--provider', multiple=True, default=['usgs', 'noaa', 'opentopography'], help='Provider(s) to search')
def search(roi, start_date, end_date, workspace, quiet, provider):
    """Search for available LiDAR data."""
    if not quiet:
        logger.info(f"Searching for data in ROI: {roi}")
        logger.info(f"Providers: {provider}")
    
    # Workspace Validation
    if not workspace:
        cwd = os.getcwd()
        if not click.confirm(f"WARNING: No --workspace specified. This will build 'catalog/' and 'data/' directories directly into: {cwd}. Proceed?"):
            raise click.Abort()
        workspace = cwd
        
    # Secure API Key Isolation: Look for .env physically inside the workspace
    env_path = os.path.join(workspace, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv() # Fallback to standard environment variables
        
    catalog_dir = os.path.join(workspace, 'catalog')
    os.makedirs(catalog_dir, exist_ok=True)
    output_manifest = os.path.join(catalog_dir, 'manifest.json')
    output_csv = os.path.join(catalog_dir, 'catalog.csv')
    output_gpkg = os.path.join(catalog_dir, 'catalog.gpkg')
    
    try:
        # Parse and validate the ROI
        roi_geom = load_roi(roi)
        if not quiet:
            logger.info(f"ROI Loaded: {roi_geom.geom_type} with bounds {roi_geom.bounds}")
        
        # Initialize Providers
        active_providers = []
        if 'opentopography' in provider:
            active_providers.append(OpenTopographyProvider())
        if 'usgs' in provider:
            active_providers.append(USGSProvider())
        if 'noaa' in provider:
            active_providers.append(NOAAProvider())
        
        final_results = []
        for p in active_providers:
            # Check access first
            if not p.check_access():
                if not quiet:
                    logger.warning(f"Skipping {p.__class__.__name__} due to access/auth issues.")
                continue

            try:
                if not quiet:
                    logger.info(f"Searching {p.__class__.__name__}...")
                results = p.search(roi_geom)
                final_results.extend(results)
            except Exception as e:
                logger.error(f"Search failed for {p.__class__.__name__}: {e}")

        # Deduplicate based on name or dataset_id
        # OpenTopography often indexes the same dataset name as USGS or NOAA
        unique_results = []
        seen_names = set()
        
        total_size_bytes = 0
        
        for item in final_results:
            name_key = str(item.get('name') or item.get('dataset_id', '')).lower()
            if not name_key or name_key in seen_names:
                continue
            seen_names.add(name_key)
            unique_results.append(item)
            
            # Impute bytes mathematically 
            if item.get('size'):
                try:
                    total_size_bytes += int(item.get('size'))
                except:
                    pass
            elif item.get('point_count'):
                try:
                    # Estimate ~8 bytes per point for a compressed LAZ v1.4 natively
                    estimated_bytes = int(item.get('point_count')) * 8
                    total_size_bytes += estimated_bytes
                    item['size'] = estimated_bytes  # Inject the estimate dynamically for the table
                except:
                    pass

        total_size_gb = total_size_bytes / (1024**3)

        # Calculate Universal Area & Density Metrics structurally first so the table can print them
        from pyproj import Geod
        from shapely.geometry import shape
        geod = Geod(ellps="WGS84")
        
        for item in unique_results:
            try:
                geom_dict = item.get('geometry')
                count = item.get('point_count')
                
                if geom_dict and not item.get('area_sqkm'):
                    poly = shape(geom_dict)
                    area_sqm = abs(geod.geometry_area_perimeter(poly)[0])
                    item['area_sqkm'] = round(area_sqm / 1e6, 2)
                    
                    if count and not item.get('point_density') and area_sqm > 0:
                        density = float(count) / area_sqm
                        item['point_density'] = round(density, 2)
            except Exception as e:
                logger.debug(f"Failed calculating density: {e}")

        # Pretty Print Table
        if not quiet:
            logger.info(f"Total Raw Datasets Found: {len(final_results)}")
            logger.info(f"Unique Datasets after deduplication: {len(unique_results)}")
            
            if unique_results:
                col_widths = {
                    "Provider": 15,
                    "Name": 38,
                    "Date": 12,
                    "Est (GB)": 10,
                    "pts/m2": 8,
                    "Area km2": 10
                }
                
                header = f" | {'Provider':<{col_widths['Provider']}} | {'Name':<{col_widths['Name']}} | {'Date':<{col_widths['Date']}} | {'Est (GB)':<{col_widths['Est (GB)']}} | {'pts/m2':<{col_widths['pts/m2']}} | {'Area km2':<{col_widths['Area km2']}} |"
                print("\n" + "=" * len(header))
                print(" LiDAR Data Search Results ")
                print("=" * len(header))
                print(header)
                print("-" * len(header))
                
                # Pre-format dates and Sort Descending
                for item in unique_results:
                    raw_date = str(item.get('date') or '').strip()
                    if not raw_date or raw_date.lower() == 'none' or raw_date == 'XXXX-XX-XX':
                        display_date = '????-??-??'
                        sort_date = '0000-00-00'
                    else:
                        if ' ' in raw_date:
                            raw_date = raw_date.split(' ')[0]
                        elif 'T' in raw_date:
                            raw_date = raw_date.split('T')[0]
                        display_date = raw_date
                        sort_date = raw_date
                        
                    # Handle USGS single-year dates natively (e.g. '2022')
                    if len(display_date) == 4 and display_date.isdigit():
                        sort_date = f"{display_date}-12-31"
                        display_date = f"{display_date}-??-??"
                        
                    item['display_date'] = display_date
                    item['sort_date'] = sort_date
                
                unique_results.sort(key=lambda k: k.get('sort_date', '0000-00-00'), reverse=True)
                
                for item in unique_results:
                    prov = str(item.get('provider', 'Unknown'))[:col_widths['Provider']]
                    name = str(item.get('name') or item.get('dataset_id', 'Unknown'))[:col_widths['Name']]
                    date = item.get('display_date')[:col_widths['Date']]
                    
                    size_gb = 'N/A'
                    if item.get('size'):
                         try:
                             size_gb = f"{int(item.get('size')) / (1024**3):.2f}"
                         except:
                             pass
                           
                    density = str(item.get('point_density', 'N/A'))[:col_widths['pts/m2']]
                    area = str(item.get('area_sqkm', 'N/A'))[:col_widths['Area km2']]
                    
                    print(f" | {prov:<{col_widths['Provider']}} | {name:<{col_widths['Name']}} | {date:<{col_widths['Date']}} | {size_gb:<{col_widths['Est (GB)']}} | {density:<{col_widths['pts/m2']}} | {area:<{col_widths['Area km2']}} |")
                
                print("=" * len(header))
                print(f" TOTAL DATASETS: {len(unique_results)} | ESTIMATED PAYLOAD: {total_size_gb:.2f} GB ")
                print("=" * len(header) + "\n")
            else:
                print("\nNo datasets found for the given ROI.\n")

        # Construct JSON Metadata Headers
        now_utc = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        if hasattr(time, 'tzname') and len(time.tzname) > 0:
            tz_name = time.tzname[time.daylight]
        else:
            tz_name = "Local"
        now_local = datetime.now().strftime(f'%Y-%m-%d %H:%M:%S {tz_name}')
        
        manifest_payload = {
            "search_parameters": {
                "roi": roi,
                "start_date": start_date,
                "end_date": end_date,
                "providers": list(provider)
            },
            "execution_metadata": {
                "timestamp_utc": now_utc,
                "timestamp_local": now_local
            },
            "datasets": unique_results 
        }

        # Save manifest
        with open(output_manifest, 'w') as f:
            json.dump(manifest_payload, f, indent=2, default=str)
            
        if not quiet:
            logger.info(f"Manifest written to {output_manifest}")
        
        # Save CSV globally
        import csv
        with open(output_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Provider', 'Name', 'DatasetID', 'Date', 'SizeMB', 'PointCount', 'PointDensity', 'AreaSqKm', 'URL'])
            for item in unique_results:
                size_mb = ""
                if item.get('size'):
                     try:
                         size_mb = f"{int(item.get('size')) / (1024*1024):.1f}"
                     except:
                         pass
                writer.writerow([
                    item.get('provider', ''),
                    item.get('name', ''),
                    item.get('dataset_id', ''),
                    item.get('date', ''),
                    size_mb,
                    item.get('point_count', ''),
                    item.get('point_density', ''),
                    item.get('area_sqkm', ''),
                    item.get('url', '')
                ])
                
        if not quiet:
            logger.info(f"CSV manifest written to {output_csv}")
        
        # Save GPKG globally
        try:
            import geopandas as gpd
            from shapely.geometry import box, shape
            from pyproj import Transformer
            from shapely.ops import transform
            
            records = []
            transformer_3857_to_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
            
            for item in unique_results:
                geom = None
                try:
                    raw_geom = item.get('geometry')
                    if raw_geom and isinstance(raw_geom, dict) and 'coordinates' in raw_geom:
                        geom = shape(raw_geom)
                    elif item.get('bounds') and len(item.get('bounds')) >= 4:
                        b = item.get('bounds')
                        geom = box(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                        
                    if geom:
                        if item.get('srs') == 'EPSG:3857':
                            geom = transform(transformer_3857_to_4326.transform, geom)
                        
                        rec = {k: str(v) for k, v in item.items() if k not in ['bounds', 'geometry', 'raw_metadata']}
                        rec['geometry'] = geom
                        records.append(rec)
                except Exception as parse_e:
                    logger.debug(f"Skipping geometry bounds parse failure: {parse_e}")
                        
            if records:
                gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
                gdf.to_file(output_gpkg, driver="GPKG")
                if not quiet:
                    logger.info(f"GeoPackage catalog written to {output_gpkg}")
            else:
                if not quiet:
                    logger.warning(f"No valid geometries found; GeoPackage not created.")
        except ImportError as e:
            logger.error(f"Missing geospatial dependencies: {e}. Ensure geopandas is installed.")
        except Exception as e:
            logger.error(f"Failed to write GeoPackage: {e}")
        
    except ROIError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))

@cli.command()
@click.option('--workspace', required=True, help='Path to existing als-finder workspace')
@click.option('--start-date', help='Override start date (YYYY-MM-DD)')
@click.option('--end-date', help='Override end date (YYYY-MM-DD)')
@click.option('--provider', multiple=True, help='Override provider(s)')
@click.option('--quiet', is_flag=True, help='Suppress output')
@click.pass_context
def update(ctx, workspace, start_date, end_date, provider, quiet):
    """Update an existing workspace catalog, preserving historical parameters and invoking atomic rollbacks."""
    catalog_dir = os.path.join(workspace, 'catalog')
    manifest_path = os.path.join(catalog_dir, 'manifest.json')
    
    # Secure API Key Isolation
    env_path = os.path.join(workspace, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()
    
    if not os.path.exists(manifest_path):
        raise click.ClickException(f"Catalog not found in workspace '{workspace}'. Run 'search' first.")
        
    # Read historic parameters
    with open(manifest_path, 'r') as f:
        data = json.load(f)
        
    params = data.get('search_parameters', {})
    historic_utc = data.get('execution_metadata', {}).get('timestamp_utc', 'unknown_time').replace(':', '').replace('-', '')
    
    # Override logic
    final_roi = params.get('roi')
    if not final_roi:
        raise click.ClickException("Historic ROI not found in manifest headers. Cannot update.")
        
    final_start = start_date if start_date else params.get('start_date')
    final_end = end_date if end_date else params.get('end_date')
    final_providers = list(provider) if provider else params.get('providers', ['usgs', 'noaa', 'opentopography'])
    
    if not quiet:
        logger.info(f"Executing Full-Replacement Update natively over Workspace: {workspace}")
        
    # Atomic Rollbacks
    backup_manifest = os.path.join(catalog_dir, f'manifest_{historic_utc}.json')
    backup_gpkg = os.path.join(catalog_dir, f'catalog_{historic_utc}.gpkg')
    backup_csv = os.path.join(catalog_dir, f'catalog_{historic_utc}.csv')
    
    if os.path.exists(manifest_path): shutil.move(manifest_path, backup_manifest)
    if os.path.exists(os.path.join(catalog_dir, 'catalog.gpkg')): shutil.move(os.path.join(catalog_dir, 'catalog.gpkg'), backup_gpkg)
    if os.path.exists(os.path.join(catalog_dir, 'catalog.csv')): shutil.move(os.path.join(catalog_dir, 'catalog.csv'), backup_csv)
    
    if not quiet:
        logger.info(f"Atomic Rollback successful. Historic catalog mapped to timestamp {historic_utc}.")
    
    # Execute native search bypass via explicit Context invocation
    ctx.invoke(search, roi=final_roi, start_date=final_start, end_date=final_end, workspace=workspace, quiet=quiet, provider=final_providers)


@cli.command()
@click.option('--manifest', help='Path to generated manifest.json from search step')
@click.option('--tile-url', help='Download a single specific tile laz URL')
@click.option('--output-dir', default='./data/input/lidar/source=usgs', help='Output directory for downloaded .laz files')
def download(manifest, tile_url, output_dir):
    """Download LiDAR data from manifest or single URL."""
    if not manifest and not tile_url:
        raise click.UsageError("Must provide either --manifest or --tile-url")
    
    logger.info(f"Starting download process to {output_dir}...")
    
    urls_to_download = []
    
    if tile_url:
        urls_to_download.append(tile_url)
    
    if manifest:
        try:
            with open(manifest, 'r') as f:
                data = json.load(f)
                datasets = data.get('datasets', data) # Support both legacy and new header structural schemas natively
                for item in datasets:
                    if item.get('url'):
                        urls_to_download.append(item['url'])
        except Exception as e:
            logger.error(f"Failed to read manifest {manifest}: {e}")
            raise click.ClickException(str(e))
            
    logger.info(f"Collected {len(urls_to_download)} tiles to download.")
    
    usgs_provider = USGSProvider()
    
    success_count = 0
    for url in urls_to_download:
        if "doi.org" in url or "opentopography.org" in url:
            logger.warning(f"Skipping OpenTopography DOI download ({url}). OT does not export direct streaming endpoints internally natively.")
            continue
            
        try:
            usgs_provider.download(tile_url=url, output_dir=output_dir)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            
    logger.info(f"Download complete. {success_count}/{len(urls_to_download)} successful.")

if __name__ == '__main__':
    cli()
