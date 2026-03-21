import click
import logging
import json
import os
import shutil
from pathlib import Path
from datetime import datetime
import time
from dotenv import load_dotenv
from als_finder.core.input_manager import load_roi, ROIError
from als_finder.providers import OpenTopographyProvider, USGSProvider, NOAAProvider

from als_finder.providers import OpenTopographyProvider, USGSProvider, NOAAProvider
from als_finder.download import generate_fetch_array, execute_fetch_array

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose execution logging')
def cli(verbose):
    """LiDAR Data Finder CLI"""
    if verbose:
        logging.getLogger().setLevel(logging.INFO)

@cli.command()
@click.option('--roi', required=False, help='Path to ROI file (GeoJSON/Shapefile) or BBox string')
@click.option('--name', help='Filter by dataset name (Exact, wildcard *Tahoe*, or prefix ~ for regex e.g. ~^USGS)')
@click.option('--date', help='Temporal filter (e.g. 2020-01-01 or 2015-01-01/2019-12-31)')
@click.option('--density', help='Point density filter pts/m2 or QL Level (e.g. 8.0, 2.0/10.0, or QL1)')
@click.option('--workspace', help='Path to project workspace directory')
@click.option('--provider', multiple=True, default=['usgs', 'noaa', 'opentopography'], help='Provider(s) to search')
@click.option('--cloud-native', is_flag=True, help='Filter exclusively for datasets that support dynamic byte-range streaming formats natively (e.g., USGS/NOAA EPT or COPC)')
@click.option('--ot-key', help='OpenTopography API Key. Will be saved to a local .env file in your working directory natively.')
def search(roi, name, date, density, workspace, provider, cloud_native, ot_key):
    """Search for available LiDAR data."""
    start_time_exec = time.time()
    
    if ot_key:
        env_path = Path.cwd() / '.env'
        with open(env_path, 'a') as f:
            f.write(f"\nOPENTOPOGRAPHY_API_KEY={ot_key}\n")
        os.environ['OPENTOPOGRAPHY_API_KEY'] = ot_key
        logger.info(f"OpenTopography API key successfully cached locally to {env_path}")
        
    if not (roi or name or date or density):
        raise click.UsageError("At least one filter (--roi, --name, --date, or --density) must be provided to execute a pipeline search securely avoiding arbitrary global extraction ceilings.")

    start_date, end_date = None, None
    if date:
        if '/' in date:
            start_date, end_date = date.split('/')
        else:
            start_date = date
            
    min_density, max_density = None, None
    if density:
        if density.upper().startswith('QL'):
            ql_map = {'QL0': 8.0, 'QL1': 8.0, 'QL2': 2.0, 'QL3': 0.5}
            min_density = ql_map.get(density.upper())
            if min_density is None:
                raise click.ClickException(f"Invalid QL specification: {density}. Use QL0, QL1, QL2, or QL3.")
        elif '/' in density:
            mn, mx = density.split('/')
            min_density, max_density = float(mn), float(mx)
        else:
            min_density = float(density)

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
        roi_geom = None
        if roi:
            roi_geom = load_roi(roi)
            logger.info(f"ROI Loaded: {roi_geom.geom_type} with bounds {roi_geom.bounds}")
        else:
            logger.warning("No ROI provided! Querying the global index natively.")
            if not click.confirm("Are you sure you want to query the entire global index without a spatial boundary?"):
                raise click.Abort()
        
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
            if not p.check_access():
                logger.warning(f"Skipping {p.__class__.__name__} due to access/auth issues.")
                continue

            try:
                logger.info(f"Searching {p.__class__.__name__}...")
                results = p.search(
                    roi=roi_geom,
                    name=name,
                    start_date=start_date,
                    end_date=end_date,
                    min_density=min_density,
                    max_density=max_density,
                    cloud_native=cloud_native
                )
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
                        if density < 0.01:
                            item['point_density'] = round(density, 4)
                        else:
                            item['point_density'] = round(density, 2)
                    elif item.get('point_density') and not count and area_sqm > 0:
                        imputed_count = int(float(item.get('point_density')) * area_sqm)
                        item['point_count'] = imputed_count
                        # Automatically track the new sizes globally
                        item['size'] = imputed_count * 8 
            except Exception as e:
                logger.debug(f"Failed calculating density: {e}")

        # Apply Name, Date and Density Filters
        filtered_results = []
        for item in unique_results:
            dataset_name_raw = item.get('name') or item.get('dataset_id', '')
            
            # 1. Dataset Name filter natively resolving fnmatch closures and compiled regex arrays
            if name:
                import fnmatch, re
                pattern = name.strip()
                target = str(dataset_name_raw).strip()
                
                if pattern.startswith('~'):
                    try:
                        if not bool(re.search(pattern[1:], target, re.IGNORECASE)):
                            continue
                    except re.error:
                        logger.warning(f"Invalid regex pattern provided: {pattern[1:]}")
                        continue
                else:
                    if not fnmatch.fnmatch(target.lower(), pattern.lower()):
                        continue

            # 2. Date filter natively intercepts standard sort_date formatting
            item_date = item.get('sort_date', '')
            if start_date and item_date < start_date:
                continue
            if end_date and item_date > end_date:
                continue
                
            # 3. Density filter inherently requires PyProj parsing execution first
            pts_m2 = item.get('point_density')
            if (min_density is not None or max_density is not None) and pts_m2 is None:
                logger.warning(f"Dropping {dataset_name_raw} due to missing density metadata.")
                continue
            if pts_m2 is not None:
                if min_density is not None and float(pts_m2) < min_density:
                    continue
                if max_density is not None and float(pts_m2) > max_density:
                    continue
                    
            filtered_results.append(item)
            
        unique_results = filtered_results
        
        # Recalculate total bytes based on filtered explicitly 
        total_size_bytes = 0
        for item in unique_results:
            if item.get('size'):
                total_size_bytes += item.get('size')
        total_size_gb = total_size_bytes / (1024**3)

        # Pretty Print Table
        logger.info(f"Total Raw Datasets Found: {len(final_results)}")
        logger.info(f"Unique Datasets after filtering: {len(unique_results)}")
        
        if unique_results:
            col_widths = {
                "Provider": 15,
                "Name": 38,
                "Date": 12,
                "Est (GB)": 10,
                "pts/m2": 8,
                "Area km2": 10
            }
            
            header = f" | {'Provider':<{col_widths['Provider']}} | {'Name':<{col_widths['Name']}} | {'Date':<{col_widths['Date']}} | {'Est (GB)':>{col_widths['Est (GB)']}} | {'pts/m2':>{col_widths['pts/m2']}} | {'Area km2':>{col_widths['Area km2']}} |"
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
                
                size_gb_str = 'N/A'
                if item.get('size') is not None:
                     try:
                         val = float(item.get('size')) / (1024**3)
                         size_gb_str = f"{val:.2f}"
                     except:
                         pass
                       
                density_str = 'N/A'
                if item.get('point_density') is not None:
                    density_str = f"{float(item.get('point_density')):.4f}"
                    
                area_str = 'N/A'
                if item.get('area_sqkm') is not None:
                    area_str = f"{float(item.get('area_sqkm')):.2f}"
                
                print(f" | {prov:<{col_widths['Provider']}} | {name:<{col_widths['Name']}} | {date:<{col_widths['Date']}} | {size_gb_str:>{col_widths['Est (GB)']}} | {density_str:>{col_widths['pts/m2']}} | {area_str:>{col_widths['Area km2']}} |")
            
            print("=" * len(header))
            query_time = time.time() - start_time_exec
            print(f" TOTAL DATASETS: {len(unique_results)} | ESTIMATED PAYLOAD: {total_size_gb:.2f} GB | QUERY TIME: {query_time:.2f}s ")
            print("-" * len(header))
            print(f" CATALOG TBL: {os.path.abspath(output_gpkg)}")
            print(f" JSON METADATA: {os.path.abspath(output_manifest)}")
            print("=" * len(header) + "\n")
        else:
            query_time = time.time() - start_time_exec
            print(f"\n=================================================================================================================\n TOTAL DATASETS: 0 | ESTIMATED PAYLOAD: 0.00 GB | QUERY TIME: {query_time:.2f}s \n=================================================================================================================\n")

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
                "name": name,
                "date": date,
                "density": density,
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
                logger.info(f"GeoPackage catalog written to {output_gpkg}")
            else:
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
@click.option('--name', help='Override dataset name filter (Supports wildcards, or regex via ~)')
@click.option('--date', help='Override temporal filter (e.g. 2020-01-01 or 2015-01-01/2019-12-31)')
@click.option('--density', help='Override point density filter or QL Level (e.g. QL1)')
@click.option('--provider', multiple=True, help='Override provider(s)')
@click.option('--ot-key', help='OpenTopography API Key. Will be saved to a local .env file in your working directory natively.')
@click.pass_context
def update(ctx, workspace, name, date, density, provider, ot_key):
    """Update an existing workspace catalog, preserving historical parameters and invoking atomic rollbacks."""
    catalog_dir = os.path.join(workspace, 'catalog')
    manifest_path = os.path.join(catalog_dir, 'manifest.json')
    
    if ot_key:
        env_path = Path.cwd() / '.env'
        with open(env_path, 'a') as f:
            f.write(f"\nOPENTOPOGRAPHY_API_KEY={ot_key}\n")
        os.environ['OPENTOPOGRAPHY_API_KEY'] = ot_key
        logger.info(f"OpenTopography API key successfully cached locally to {env_path}")
    
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
        
    final_name = name if name else params.get('name')
    final_date = date if date else params.get('date')
    final_density = density if density else params.get('density')
    final_providers = list(provider) if provider else params.get('providers', ['usgs', 'noaa', 'opentopography'])
    
    logger.info(f"Executing Full-Replacement Update natively over Workspace: {workspace}")
        
    # Atomic Rollbacks
    backup_manifest = os.path.join(catalog_dir, f'manifest_{historic_utc}.json')
    backup_gpkg = os.path.join(catalog_dir, f'catalog_{historic_utc}.gpkg')
    backup_csv = os.path.join(catalog_dir, f'catalog_{historic_utc}.csv')
    
    if os.path.exists(manifest_path): shutil.move(manifest_path, backup_manifest)
    if os.path.exists(os.path.join(catalog_dir, 'catalog.gpkg')): shutil.move(os.path.join(catalog_dir, 'catalog.gpkg'), backup_gpkg)
    if os.path.exists(os.path.join(catalog_dir, 'catalog.csv')): shutil.move(os.path.join(catalog_dir, 'catalog.csv'), backup_csv)
    
    logger.info(f"Atomic Rollback successful. Historic catalog mapped to timestamp {historic_utc}.")
    
    # Execute native search bypass via explicit Context invocation
    ctx.invoke(search, roi=final_roi, name=final_name, date=final_date, density=final_density, workspace=workspace, provider=final_providers)


@cli.command()
@click.pass_context
@click.option('--workspace', required=True, help='Path to target workspace directory containing the manifest.json')
@click.option('--roi', help='Path to spatial boundary file (.geojson, .gpkg, .shp) to dynamically mask downloads.')
@click.option('--name', help='Filter by dataset name (Exact, wildcard *Tahoe*, or prefix ~ for regex e.g. ~^USGS)')
@click.option('--date', help='Date filter YYYY-MM-DD or range YYYY-MM-DD/YYYY-MM-DD')
@click.option('--density', help='Point density filter pts/m2 or QL Level (e.g. 8.0, 2.0/10.0, or QL1)')
@click.option('--provider', multiple=True, default=['usgs', 'noaa', 'opentopography'], help='Provider(s) to search')
@click.option('--cloud-native', is_flag=True, help='Filter exclusively for datasets that support dynamic byte-range streaming formats natively (e.g., USGS/NOAA EPT or COPC)')
@click.option('--ot-key', help='OpenTopography API Key. Will be saved to a local .env file in your working directory natively.')
@click.option('--execute', is_flag=True, help='Disable dry-run safety and physically pull binary formats to the local drive natively.')
@click.option('--full', is_flag=True, help='Bypass spatial ROI intersections and pull the entirely comprehensive upstream dataset payload natively.')
def download(ctx, workspace, roi, name, date, density, provider, cloud_native, ot_key, execute, full):
    """Generate target fetch arrays or physically download filtered binary segments directly to the Hive local cache."""
    workspace_path = Path(workspace)
    fetch_array_path = workspace_path / 'catalog' / 'fetch_array.csv'
    manifest_path = workspace_path / 'catalog' / 'manifest.json'
    
    # Always naturally generate the dry-run array matrix organically unless explicitly instructed to blindly execute 
    # (And even then, if it doesn't physically exist, mathematically generate it first)
    if not fetch_array_path.exists() or not execute:
        
        if not manifest_path.exists():
            logger.info(f"No existing manifest.json found at {workspace_path}. Seamlessly spawning a dynamic search...")
            ctx.invoke(search, roi=roi, name=name, date=date, density=density, workspace=workspace, provider=provider, cloud_native=cloud_native, ot_key=ot_key)
            
            if not manifest_path.exists():
                logger.error("The internal search failed to establish a rigid catalog boundary. Aborting download generation.")
                sys.exit(1)
                
        logger.info("Executing Mode C: Array Fetch Generation (Dry-Run)")
        generate_fetch_array(workspace_path=workspace_path, roi_path=roi, full_acquisition=full)
        
    if execute:
        logger.info("Executing Mode A/B: Physical Core Download Protocol")
        execute_fetch_array(workspace_path=workspace_path)

if __name__ == '__main__':
    cli()
