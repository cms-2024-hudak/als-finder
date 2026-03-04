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
@click.option('--provider', multiple=True, default=['opentopography', 'usgs', 'noaa'], help='Provider(s) to search')
def search(roi, start_date, end_date, output_manifest, provider):
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

        # Summary Output
        logger.info(f"Total Datasets Found: {len(final_results)}")
        
        # Dump to console or file (TODO: Format this better)
        print(json.dumps(final_results, indent=2, default=str))

        # Save manifest
        with open(output_manifest, 'w') as f:
            json.dump(final_results, f, indent=2, default=str)
        logger.info(f"Manifest written to {output_manifest}")
        
    except ROIError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))

@cli.command()
@click.option('--manifest', help='Path to generated manifest.json from search step')
@click.option('--tile-url', help='Download a single specific tile laz URL')
@click.option('--output-dir', default='./data/input/tiles', help='Output directory for downloaded .laz files')
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
    
    # Instantiate providers (assuming USGS for direct LAZ downloads initially)
    usgs_provider = USGSProvider()
    # Add OT logic here if needed later when OT provides direct URL links
    
    success_count = 0
    for url in urls_to_download:
        try:
            # Simple heuristic: if it looks like a USGS S3/TNM link, use USGS
            # For now, we only have USGS direct tile downloading implemented fully
            usgs_provider.download(tile_url=url, output_dir=output_dir)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            
    logger.info(f"Download complete. {success_count}/{len(urls_to_download)} successful.")

if __name__ == '__main__':
    cli()
