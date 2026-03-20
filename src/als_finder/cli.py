import click
import logging
import json
from als_finder.core.input_manager import load_roi, ROIError
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
@click.option('--output-manifest', default='./manifest.json', help='Output JSON manifest path')
@click.option('--output-csv', help='Output CSV manifest path (optional)')
@click.option('--output-gpkg', help='Output GeoPackage catalog path (optional)')
@click.option('--provider', multiple=True, default=['opentopography', 'usgs', 'noaa'], help='Provider(s) to search')
def search(roi, start_date, end_date, output_manifest, output_csv, output_gpkg, provider):
    """Search for available LiDAR data."""
    logger.info(f"Searching for data in ROI: {roi}")
    logger.info(f"Providers: {provider}")
    
    try:
        # Parse and validate the ROI
        roi_geom = load_roi(roi)
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
                logger.warning(f"Skipping {p.__class__.__name__} due to access/auth issues.")
                continue

            try:
                logger.info(f"Searching {p.__class__.__name__}...")
                results = p.search(roi_geom)
                final_results.extend(results)
            except Exception as e:
                logger.error(f"Search failed for {p.__class__.__name__}: {e}")

        # Deduplication and Summary Output
        logger.info(f"Total Raw Datasets Found: {len(final_results)}")
        
        # Deduplicate based on name or dataset_id
        # OpenTopography often indexes the same dataset name as USGS or NOAA
        unique_results = []
        seen_names = set()
        
        for item in final_results:
            name_key = str(item.get('name') or item.get('dataset_id', '')).lower()
            if not name_key or name_key in seen_names:
                continue
            seen_names.add(name_key)
            unique_results.append(item)

        logger.info(f"Unique Datasets after deduplication: {len(unique_results)}")

        # Pretty Print Table
        if unique_results:
            col_widths = {
                "Provider": 15,
                "Name": 40,
                "Date": 22,
                "Size (MB)": 10
            }
            
            header = f" | {'Provider':<{col_widths['Provider']}} | {'Name':<{col_widths['Name']}} | {'Date':<{col_widths['Date']}} | {'Size (MB)':<{col_widths['Size (MB)']}} |"
            print("\n" + "=" * len(header))
            print(" LiDAR Data Search Results ")
            print("=" * len(header))
            print(header)
            print("-" * len(header))
            
            for item in unique_results:
                prov = str(item.get('provider', 'Unknown'))[:col_widths['Provider']]
                name = str(item.get('name') or item.get('dataset_id', 'Unknown'))[:col_widths['Name']]
                date = str(item.get('date') or 'N/A')[:col_widths['Date']]
                size_mb = 'N/A'
                if item.get('size'):
                     try:
                         size_mb = f"{int(item.get('size')) / (1024*1024):.1f}"
                     except:
                         pass
                
                print(f" | {prov:<{col_widths['Provider']}} | {name:<{col_widths['Name']}} | {date:<{col_widths['Date']}} | {size_mb:<{col_widths['Size (MB)']}} |")
            
            print("=" * len(header) + "\n")
        else:
            print("\nNo datasets found for the given ROI.\n")

        # Save manifest
        with open(output_manifest, 'w') as f:
            json.dump(unique_results, f, indent=2, default=str)
        logger.info(f"Manifest written to {output_manifest}")
        
        # Save CSV if requested
        if output_csv:
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
        
        # Save GPKG if requested
        if output_gpkg:
            try:
                import geopandas as gpd
                from shapely.geometry import box, shape
                from pyproj import Transformer
                from shapely.ops import transform
                
                records = []
                # OT frequently assigns EPSG:3857 coordinates while STAC enforces EPSG:4326 
                # Create a physical mathematical transformer resolving the QGIS mixed-coordinate sliver bugs!
                transformer_3857_to_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                
                for item in unique_results:
                    geom = None
                    try:
                        # 1. Prefer full polygon multi-ring arrays natively (giving the user the true irregular tile outlines)
                        raw_geom = item.get('geometry')
                        if raw_geom and isinstance(raw_geom, dict) and 'coordinates' in raw_geom:
                            geom = shape(raw_geom)
                            
                        # 2. Fallback mathematically to rectangular bounds
                        elif item.get('bounds') and len(item.get('bounds')) >= 4:
                            b = item.get('bounds')
                            geom = box(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                            
                        # Process generic alignment mapping
                        if geom:
                            # Re-map native Web Mercator OT bounds strictly back to WGS84 Lat/Lon
                            if item.get('srs') == 'EPSG:3857':
                                geom = transform(transformer_3857_to_4326.transform, geom)
                            
                            # Flatten attributes natively filtering unmapped arrays mapping cleanly
                            rec = {k: str(v) for k, v in item.items() if k not in ['bounds', 'geometry', 'raw_metadata']}
                            rec['geometry'] = geom
                            records.append(rec)
                    except Exception as parse_e:
                        logger.debug(f"Skipping geometry bounds parse failure: {parse_e}")
                            
                if records:
                    # Enforce strict uniform WGS84
                    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
                    gdf.to_file(output_gpkg, driver="GPKG")
                    logger.info(f"GeoPackage catalog written to {output_gpkg}")
                else:
                    logger.warning(f"No valid geometries found; GeoPackage {output_gpkg} not created.")
            except ImportError as e:
                logger.error(f"Missing geospatial dependencies: {e}. Ensure geopandas, pyproj, and shapely are installed.")
            except Exception as e:
                logger.error(f"Failed to write GeoPackage: {e}")
        
    except ROIError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))

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
                for item in data:
                    if item.get('url'):
                        urls_to_download.append(item['url'])
        except Exception as e:
            logger.error(f"Failed to read manifest {manifest}: {e}")
            raise click.ClickException(str(e))
            
    logger.info(f"Collected {len(urls_to_download)} tiles to download.")
    
    # Instantiate providers (assuming USGS for direct LAZ/json dynamically mapped array downloads natively)
    usgs_provider = USGSProvider()
    
    success_count = 0
    for url in urls_to_download:
        if "doi.org" in url or "opentopography.org" in url:
            logger.warning(f"[Issue 2 Fixed] Skipping OpenTopography DOI download ({url}). OT does not export direct streaming endpoints internally natively.")
            continue
            
        try:
            usgs_provider.download(tile_url=url, output_dir=output_dir)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            
    logger.info(f"Download complete. {success_count}/{len(urls_to_download)} successful.")

if __name__ == '__main__':
    cli()
