import click
import logging
import json
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime
import time
import importlib.resources as pkg_resources
from dotenv import load_dotenv
from als_finder.core.input_manager import load_roi, ROIError
from als_finder.providers import OpenTopographyProvider, USGSProvider, NOAAProvider

from als_finder.providers import OpenTopographyProvider, USGSProvider, NOAAProvider
from als_finder.download import generate_fetch_array, execute_fetch_array

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

def parse_comma_separated(ctx, param, value):
    """Click callback to parse comma-separated strings into a flattened tuple."""
    if not value:
        return value
    parsed = []
    for item in value:
        parsed.extend([x.strip() for x in item.split(',') if x.strip()])
    return tuple(parsed)

@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose execution logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress standard logging to print exact payloads only.')
def cli(verbose, quiet):
    """LiDAR Data Finder CLI"""
    if verbose:
        logging.getLogger().setLevel(logging.INFO)
    elif quiet:
        logging.getLogger().setLevel(logging.WARNING)
@cli.command(name='get-example-roi')
def get_example_roi():
    """Extract the bundled example ROI to your current working directory."""
    try:
        if sys.version_info >= (3, 9):
            source_path = pkg_resources.files('als_finder.data').joinpath('ltbmu_boundary.gpkg')
            with pkg_resources.as_file(source_path) as gpkg_file:
                dest_path = Path.cwd() / 'ltbmu_boundary.gpkg'
                shutil.copy2(gpkg_file, dest_path)
        else:
            # Fallback for Python 3.8
            import pkg_resources as legacy_pkg_resources
            source_path = legacy_pkg_resources.resource_filename('als_finder', 'data/ltbmu_boundary.gpkg')
            dest_path = Path.cwd() / 'ltbmu_boundary.gpkg'
            shutil.copy2(source_path, dest_path)
            
        click.echo(click.style(f"Success! Example ROI extracted to: {dest_path}", fg="green"))
    except Exception as e:
        logger.error(f"Failed to extract example ROI. Ensure the package was installed correctly. Error: {e}")
        sys.exit(1)

@cli.command()
@click.option('--roi', required=False, help='Path to ROI file (GeoJSON/Shapefile) or BBox string')
@click.option('--name', help='Filter by dataset name (Exact, wildcard *Tahoe*, or prefix ~ for regex e.g. ~^USGS)')
@click.option('--date', help='Temporal filter (e.g. 2020-01-01 or 2015-01-01/2019-12-31)')
@click.option('--density', help='Point density filter pts/m2 or QL Level (e.g. 8.0, 2.0/10.0, or QL1)')
@click.option('--workspace', help='Path to project workspace directory')
@click.option('--provider', multiple=True, default=['USGS_EPT', 'NOAA_STAC', 'OpenTopography'], callback=parse_comma_separated, help='Provider(s) to search (comma-separated allowed)')
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
        if '/' not in date:
            raise click.UsageError("Temporal mapping via --date must strictly contain a slash '/' delimiter isolating bounds. Options: '2020-01-01/' (after), '/2020-01-01' (before), or '2015-01-01/2020-01-01' (explicit range).")
        
        start_date, end_date = date.split('/', 1)
        start_date = start_date.strip() if start_date.strip() else None
        end_date = end_date.strip() if end_date.strip() else None
            
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
        if 'OpenTopography' in provider:
            active_providers.append(OpenTopographyProvider())
        if 'USGS_EPT' in provider:
            active_providers.append(USGSProvider())
        if 'NOAA_STAC' in provider:
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
                        calc_density = float(count) / area_sqm
                        if calc_density < 0.01:
                            item['point_density'] = round(calc_density, 4)
                        else:
                            item['point_density'] = round(calc_density, 2)
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
            raw_date_test = str(item.get('date') or '').strip()
            if not raw_date_test or raw_date_test.lower() == 'none' or raw_date_test == 'XXXX-XX-XX':
                item_date = '0000-00-00'
            else:
                if ' ' in raw_date_test: raw_date_test = raw_date_test.split(' ')[0]
                elif 'T' in raw_date_test: raw_date_test = raw_date_test.split('T')[0]
                
                if len(raw_date_test) == 4 and raw_date_test.isdigit():
                    item_date = f"{raw_date_test}-12-31"
                else:
                    item_date = raw_date_test
                    
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
                disp_name = str(item.get('name') or item.get('dataset_id', 'Unknown'))[:col_widths['Name']]
                disp_date = item.get('display_date')[:col_widths['Date']]
                
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
                
                print(f" | {prov:<{col_widths['Provider']}} | {disp_name:<{col_widths['Name']}} | {disp_date:<{col_widths['Date']}} | {size_gb_str:>{col_widths['Est (GB)']}} | {density_str:>{col_widths['pts/m2']}} | {area_str:>{col_widths['Area km2']}} |")
            
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
@click.option('--provider', multiple=True, callback=parse_comma_separated, help='Override provider(s) (comma-separated allowed)')
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
    try:
        ctx.invoke(search, roi=final_roi, name=final_name, date=final_date, density=final_density, workspace=workspace, provider=final_providers)
    except Exception as e:
        logger.error(f"Update failed during sub-search execution: {e}. Restoring previous catalog state natively.")
        # Roll forward to restore state
        if os.path.exists(backup_manifest): shutil.move(backup_manifest, manifest_path)
        if os.path.exists(backup_gpkg): shutil.move(backup_gpkg, os.path.join(catalog_dir, 'catalog.gpkg'))
        if os.path.exists(backup_csv): shutil.move(backup_csv, os.path.join(catalog_dir, 'catalog.csv'))
        raise click.ClickException(f"Update failed and was safely rolled back. Original error: {str(e)}")


@cli.command()
@click.pass_context
@click.option('--workspace', required=True, help='Path to target workspace directory containing the manifest.json')
@click.option('--roi', help='Path to spatial boundary file (.geojson, .gpkg, .shp) to dynamically mask downloads.')
@click.option('--name', help='Filter by dataset name (Exact, wildcard *Tahoe*, or prefix ~ for regex e.g. ~^USGS)')
@click.option('--date', help='Date filter YYYY-MM-DD or range YYYY-MM-DD/YYYY-MM-DD')
@click.option('--density', help='Point density filter pts/m2 or QL Level (e.g. 8.0, 2.0/10.0, or QL1)')
@click.option('--provider', multiple=True, default=['USGS_EPT', 'NOAA_STAC', 'OpenTopography'], callback=parse_comma_separated, help='Provider(s) to search (comma-separated allowed)')
@click.option('--cloud-native', is_flag=True, help='Filter exclusively for datasets that support dynamic byte-range streaming formats natively (e.g., USGS/NOAA EPT or COPC)')
@click.option('--ot-key', help='OpenTopography API Key. Will be saved to a local .env file in your working directory natively.')
@click.option('--execute', is_flag=True, help='Disable dry-run safety and physically pull binary formats to the local drive natively.')
@click.option('--full', is_flag=True, help='Bypass spatial ROI intersections and pull the entirely comprehensive upstream dataset payload natively.')
@click.option('--standardize', is_flag=True, help='Execute PDAL standardization concurrently after extracting binaries.')
@click.option('--crs', help='Specify target output projection for normalization (e.g. EPSG:3857, EPSG:5070, or auto-utm)')
@click.option('--stac', is_flag=True, help='Dynamically generate PySTAC schema hierarchies out of the standardized payloads natively.')
@click.option('--quicklook', is_flag=True, help='Generate rapid 2D quicklook previews for QA/QC spot-checking.')
@click.option('--preserve-raw', is_flag=True, help='Preserve the raw .laz binaries after successful standardization. By default, raw files are purged to save space.')
@click.option('--workers', type=int, help='Override the number of concurrent thread workers. Defaults to dynamic scaling based on os.cpu_count()')
@click.option('--overwrite', is_flag=True, help='Force overwrite of existing files instead of skipping them.')
def download(ctx, workspace, roi, name, date, density, provider, cloud_native, ot_key, execute, full, standardize, crs, stac, quicklook, preserve_raw, workers, overwrite):
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
                
        logger.info("Executing Mode C: Array Fetch Generation (Dry-Run)" if not execute else "Executing Mode C: Array Fetch Generation")
        generate_fetch_array(workspace_path=workspace_path, roi_path=roi, full_acquisition=full, execute=execute)
        
    if execute:
        logger.info("Executing Mode A/B: Physical Core Download Protocol")
        execute_fetch_array(workspace_path=workspace_path, workers=workers, overwrite=overwrite)
        if standardize:
            logger.info("Executing Mode D: PDAL Standardization")
            ctx.invoke(standardize_cmd, workspace=workspace, crs=crs, roi=roi, stac=stac, quicklook=quicklook, preserve_raw=preserve_raw, workers=workers, overwrite=overwrite)
        elif stac or quicklook:
            logger.warning("STAC Generation and Quicklooks explicitly require standardized .copc.laz entities. Ignoring flags without --standardize.")

@cli.command('standardize')
@click.option('--workspace', required=True, type=click.Path(exists=True), help='Path to your local project workspace.')
@click.option('--crs', default='native', help='Target Coordinate Reference System. Defaults to "native" (trusts provider), falling back to dynamic UTM based on acquisition centroid.')
@click.option('--roi', default=None, help='Optional path to ROI geometry to geometrically slice the point cloud footprint natively.')
@click.option('--stac/--no-stac', default=True, help='Generate STAC compliant metadata schemas for the final standardized matrix.')
@click.option('--quicklook', is_flag=True, help='Generate rapid 2D quicklook previews for QA/QC spot-checking.')
@click.option('--preserve-raw', is_flag=True, help='Preserve the raw .laz binaries after successful standardization. By default, raw files are purged to save space.')
@click.option('--workers', type=int, help='Override the number of concurrent thread workers. Defaults to dynamic scaling based on os.cpu_count()')
@click.option('--tile-size', type=int, default=0, help='Core tile size in meters for spatial orchestration. Defaults to 0 (dynamic based on density).')
@click.option('--buffer-size', type=int, default=30, help='Overlap buffer size in meters to prevent edge artifacts. Defaults to 30m to preserve memory constraints.')
@click.option('--grid-crs', default='EPSG:3857', help='CRS for the orchestration grid. Defaults to EPSG:3857.')
@click.option('--overwrite', is_flag=True, help='Force overwrite of existing standardized files instead of skipping them.')
@click.option('--classifier', type=click.Choice(['smrf', 'csf', 'hybrid-dual', 'none']), default='hybrid-dual', help='Ground classification algorithm to use. Defaults to hybrid-dual.')
@click.option('--tile-index', type=int, default=None, help='Execute a single specific tile index (for HPC Job Arrays).')
@click.option('--csf-resolution', type=float, default=1.0, help='CSF grid resolution.')
@click.option('--csf-step', type=float, default=0.5, help='CSF step size.')
@click.option('--normal-threshold-z', type=float, default=0.85, help='NormalZ threshold to distinguish steep natural terrain from horizontal artificial structures in hybrid-dual.')
def standardize_cmd(workspace, crs, roi, stac, quicklook, preserve_raw, workers, tile_size, buffer_size, grid_crs, overwrite, classifier, tile_index, csf_resolution, csf_step, normal_threshold_z):
    """Execute PDAL Standardization matrices on locally downloaded LiDAR binaries."""
    workspace_path = Path(workspace)
    fetch_array_path = workspace_path / 'catalog' / 'fetch_array.csv'
    
    if not fetch_array_path.exists():
        raise click.ClickException(f"Missing fetch array in {workspace}. Execute a download structure first.")
        
    import subprocess
    try:
        subprocess.run(['pdal', '--version'], capture_output=True, check=True)
    except Exception:
        raise click.ClickException("pdal library missing. You must install 'pdal' and 'python-pdal' via Conda to standardize.")
        
    logger.info("Initializing PDAL Pipeline Standardization")
    if crs == 'native':
        logger.info("Target CRS is native (trusts provider). Pipeline will run in native coordinates and reproject to EPSG:3857 at the end.")
    elif crs == 'auto-utm-centroid':
        if not roi:
            raise click.ClickException("Cannot compute 'auto-utm-centroid' without providing an --roi geometry.")
        from als_finder.core.input_manager import load_roi
        import math
        roi_gdf = load_roi(roi)
        # load_roi returns a Shapely Polygon in EPSG:4326
        centroid = roi_gdf.centroid
        lon, lat = centroid.x, centroid.y
        zone = math.floor((lon + 180) / 6.0) + 1
        epsg = 32600 + zone if lat >= 0 else 32700 + zone
        crs = f"EPSG:{epsg}"
        logger.info(f"Target CRS dynamically calculated from overall ROI centroid: {crs}")
    else:
        logger.info(f"Target CRS strictly enforced: {crs}")
        
    from als_finder.core.standardization import generate_grid, run_pdal_standardization, run_final_copc_merge
    import csv
    import subprocess
    import geopandas as gpd
    import psutil
    from concurrent.futures import ThreadPoolExecutor
    from tqdm import tqdm
    import shutil
    from als_finder.core.input_manager import load_roi
    
    # Phase 1: Universal Hive Ingestion
    datasets = set()
    all_fetch_rows = []
    with open(fetch_array_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_fetch_rows.append(row)
            target_raw = row['target_path']
            if '|' in target_raw:
                target_str, _ = target_raw.split('|')
                target_path = Path(target_str)
            else:
                target_path = Path(target_raw)
            provider = row['provider']
            dataset_folder = target_path.parent.name
            if 'dataset=' in dataset_folder:
                dataset = dataset_folder.replace('dataset=', '')
                datasets.add((provider, dataset))
                
    ctx = click.get_current_context(silent=True)
    disable_tqdm = ctx.params.get('quiet', False) if ctx and hasattr(ctx, 'params') else False
    
    import json
    manifest_path = workspace_path / 'catalog' / 'manifest.json'
    dataset_densities = {}
    if manifest_path.exists():
        with open(manifest_path, 'r') as f:
            try:
                manifest_data = json.load(f)
                for ds in manifest_data.get('datasets', []):
                    dataset_densities[ds.get('dataset_id')] = ds.get('point_density')
            except Exception as e:
                logger.warning(f"Failed to parse manifest for density scaling: {e}")
    
    for provider, dataset in datasets:
        logger.info(f"Standardizing dataset: {dataset} from {provider}")
        final_copc_path = workspace_path / "data" / "standardized" / f"provider={provider}" / f"dataset={dataset}" / f"{dataset}.copc.laz"
        
        if final_copc_path.exists() and not overwrite:
            logger.info(f"Standardized COPC already exists for {dataset}. Skipping. Use --overwrite to force rebuild.")
            continue

        raw_dir = workspace_path / "data" / "raw" / f"provider={provider}" / f"dataset={dataset}"
        catalog_dir = workspace_path / "catalog" / "indices" / f"provider={provider}" / f"dataset={dataset}"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        raw_index_path = catalog_dir / "raw_index.gpkg"
        
        import glob
        laz_files = glob.glob(f"{raw_dir}/*.laz") + glob.glob(f"{raw_dir}/*.las") + glob.glob(f"{raw_dir}/*.copc.laz")
        
        if laz_files:
            # We have local files, rebuild index for local processing
            if raw_index_path.exists():
                raw_index_path.unlink()
            file_list = "\n".join(laz_files)
            try:
                subprocess.run(
                    ['pdal', 'tindex', 'create', str(raw_index_path), '-f', 'GPKG', '--t_srs', grid_crs, '--lyr_name', 'pdal', '--fast_boundary', '-s'], 
                    input=file_list.encode('utf-8'), 
                    check=True,
                    stderr=subprocess.PIPE
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to create raw index for {dataset}: {e.stderr.decode('utf-8')}")
                continue
        elif raw_index_path.exists():
            # We have a remote index, use it directly!
            logger.info(f"No local files found in {raw_dir}, but remote index exists. Streaming from remote source.")
        else:
            # We don't have local files or an index, so we generate a virtual index for on-demand streaming!
            features = []
            for row in all_fetch_rows:
                ds_id = row.get('dataset_id') or row.get('name')
                p_name = row.get('provider')
                if ds_id == dataset and p_name == provider:
                    url_str = row['source_url']
                    if roi:
                        b_poly = load_roi(roi)
                    else:
                        from shapely.geometry import box
                        b_poly = box(-180, -90, 180, 90)
                    features.append({"location": url_str, "geometry": b_poly})
            
            if features:
                gdf_virtual = gpd.GeoDataFrame(features, crs="EPSG:4326")
                gdf_virtual = gdf_virtual.to_crs(grid_crs)
                gdf_virtual.to_file(raw_index_path, driver="GPKG")
                logger.info(f"Generated virtual remote index for on-demand streaming of {dataset}.")
            else:
                logger.warning(f"No LiDAR files found in {raw_dir} and no remote index. Skipping dataset.")
                continue
        
        # Phase 2: Python Orchestration (The dynamic Grid)
        if roi:
            try:
                roi_poly = load_roi(roi)
                gdf = gpd.GeoDataFrame(index=[0], crs='EPSG:4326', geometry=[roi_poly])
                gdf = gdf.to_crs(grid_crs)
            except Exception as e:
                logger.warning(f"ROI parsing failed: {e}. Falling back to dataset bounds.")
                gdf = gpd.read_file(raw_index_path)
        else:
            gdf = gpd.read_file(raw_index_path)
            
        actual_tile_size = tile_size
        if tile_size == 0:
            density = dataset_densities.get(dataset)
            if density is None:
                actual_tile_size = 512
            else:
                try:
                    d_val = float(density)
                    if d_val > 20.0:
                        actual_tile_size = 128
                    elif d_val > 5.0:
                        actual_tile_size = 256
                    else:
                        actual_tile_size = 512
                except (ValueError, TypeError):
                    actual_tile_size = 512
            logger.info(f"Dynamic spatial scaling enabled: [{dataset}] density {density} pts/m2 -> using {actual_tile_size}m tiles.")
            
        grid = generate_grid(gdf, tile_size=actual_tile_size, buffer_size=buffer_size)
        
        # Phase 3: RAM-Aware Distributed Processing
        available_ram_gb = psutil.virtual_memory().available / (1024**3)
        if classifier == 'smrf':
            # Dynamic gridding mathematically caps RAM
            ram_per_worker = 1.5
        else:
            # PDAL filters.csf memory usage scales heavily with tile area.
            ram_per_worker = 1.5 if actual_tile_size <= 256 else 3.0
        max_ram_workers = int((available_ram_gb - 3.0) / ram_per_worker)
        if max_ram_workers < 1:
            max_ram_workers = 1
            
        cpu_cores = os.cpu_count() or 4
        if workers is None:
            # Scale directly based on CPU and RAM limits
            n_workers = min(cpu_cores, max_ram_workers)
        else:
            n_workers = workers
            
        interim_dir = workspace_path / "data" / "interim" / f"provider={provider}" / f"dataset={dataset}"
        interim_dir.mkdir(parents=True, exist_ok=True)
        
        current_density = dataset_densities.get(dataset)
        def worker_fn(item):
            idx, (core_poly, buffered_poly) = item
            out_path = interim_dir / f"tile_{idx}.laz"
            success = run_pdal_standardization(raw_index_path, out_path, crs, core_poly, buffered_poly, provider, grid_crs, classifier, current_density, csf_resolution, csf_step, normal_threshold_z)
            return success
            
        if tile_index is not None:
            if tile_index < 0 or tile_index >= len(grid):
                logger.error(f"Tile index {tile_index} is out of bounds for grid of size {len(grid)}.")
                continue
            logger.info(f"[HPC BATCH MODE] Executing strictly on tile index {tile_index} of {len(grid)-1}")
            item = (tile_index, grid[tile_index])
            worker_fn(item)
            logger.info(f"[HPC BATCH MODE] Tile {tile_index} complete. Exiting DAG node.")
            continue
            
        logger.info(f"Processing {len(grid)} tiles using {n_workers} concurrent workers (RAM bounds: {max_ram_workers})...")
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            list(tqdm(executor.map(worker_fn, enumerate(grid)), total=len(grid), desc=f"Standardizing {dataset}", disable=disable_tqdm))
            
        # Phase 4: Final COPC Aggregation
        interim_index_path = catalog_dir / "interim_index.gpkg"
        if interim_index_path.exists():
            interim_index_path.unlink()
            
        # Check if any interim files exist
        interim_files = list(interim_dir.glob("*.laz"))
        if not interim_files:
            logger.warning(f"No standardized tiles generated for {dataset}. Skipping merge.")
            try:
                shutil.rmtree(interim_dir)
            except Exception as e:
                logger.debug(f"Failed to remove empty interim directory: {e}")
            continue
            
        logger.info(f"Merging {len(interim_files)} tiles into monolithic COPC...")
        if interim_index_path.exists():
            interim_index_path.unlink()
        subprocess.run(['pdal', 'tindex', 'create', str(interim_index_path), '-f', 'GPKG', '--t_srs', crs, '--lyr_name', 'pdal', '--fast_boundary', '--filespec', f"{interim_dir}/*.laz"], check=True)
        success = run_final_copc_merge(interim_index_path, final_copc_path, crs=crs, workers=n_workers)
        
        # Cleanup ONLY if successful to prevent silent data loss
        if success:
            shutil.rmtree(interim_dir)
            if not preserve_raw:
                try:
                    shutil.rmtree(raw_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanly purge raw data: {e}")
        else:
            logger.error(f"Merge failed for {dataset}. Interim data preserved in {interim_dir} for debugging.")
                
    logger.info("[SUCCESS] Standardization Complete.")
    
    if stac:
        logger.info("Executing Mode E: STAC Schema Generation natively...")
        from als_finder.core.stac_generator import generate_catalog
        generate_catalog(workspace_path)
        
    logger.info("Executing Mode G: Local Catalog Footprint Generation natively...")
    from als_finder.core.local_catalog import generate_local_catalog
    generate_local_catalog(workspace_path, crs)
        
    if quicklook:
        logger.info("Executing Mode F: Quicklook QA/QC Generation natively...")
        from als_finder.core.quicklooks import generate_quicklooks
        generate_quicklooks(workspace_path)

@cli.command('clean')
@click.option('--workspace', required=True, type=click.Path(exists=True), help='Path to target workspace directory to clean.')
def clean_cmd(workspace):
    """Clean the specified workspace by removing scratch and interim data."""
    workspace_path = Path(workspace)
    if not workspace_path.exists():
        logger.warning(f"Workspace {workspace} does not exist.")
        return

    logger.info(f"Automatically cleaning up workspace: {workspace_path}")
    try:
        shutil.rmtree(workspace_path)
        logger.info(f"Successfully cleaned workspace: {workspace_path}")
    except Exception as e:
        logger.error(f"Failed to clean workspace: {e}")
        raise click.ClickException(str(e))

if __name__ == '__main__':
    cli()
